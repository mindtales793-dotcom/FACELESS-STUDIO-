"""Planejador de cenas — divide um SRT/roteiro em cenas e gera consultas de busca.

Cada bloco do SRT vira uma cena com {início, fim, texto, palavras_chave, consultas,
descricao_visual, mídia}. Um passo de LLM gera 2–4 consultas de busca curtas (em
inglês e no idioma do vídeo) e uma descrição visual por cena.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from scenes import parse_srt, group_cues, _scene
from styles import PACING

API = "https://generativelanguage.googleapis.com/v1beta"
IMAGE_MODEL = os.getenv("FLOW_IMAGE_MODEL", "gemini-2.5-flash-image")
TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")


def _gemini_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    return key


def _headers() -> dict[str, str]:
    key = _gemini_key()
    if not key:
        return {}
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _detect_lang(texto: str) -> str:
    """Detecta idioma simples: pt se tiver palavras comuns em português, senão en."""
    t = texto.lower()
    pt_words = {"e", "de", "a", "o", "que", "do", "da", "em", "um", "para", "é", "com", "não", "na", "por", "os", "as", "se", "um"}
    hits = sum(1 for w in pt_words if f" {w} " in f" {t} ")
    return "pt" if hits >= 3 else "en"


def parse_srt_to_cenas(srt_text: str) -> list[dict[str, Any]]:
    """Converte um SRT em lista de cenas com timestamps.

    Se o texto não estiver no formato SRT (sem blocos numerados com -->),
    divide por parágrafos e atribui tempos sequenciais simulados.
    """
    texto = str(srt_text or "").strip()
    if not texto:
        return []
    if "-->" not in texto:
        paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
        if not paragrafos:
            paragrafos = [texto]
        cenas = []
        tempo_atual = 0.0
        duracao_por_paragrafo = 6.0
        for i, para in enumerate(paragrafos):
            cenas.append({
                "id": f"cena_{i}",
                "inicio": tempo_atual,
                "fim": tempo_atual + duracao_por_paragrafo,
                "texto": para,
                "palavras_chave": [],
                "consultas": [],
                "descricao_visual": "",
                "midia": None,
                "status": "pendente",
                "provedor": None,
                "asset_id": None,
                "url_origem": None,
                "licenca": None,
                "autor": None,
            })
            tempo_atual += duracao_por_paragrafo
        return cenas
    cues = parse_srt(texto)
    cenas = []
    for i, cue in enumerate(cues):
        texto_cue = str(cue.get("text", ""))
        cenas.append({
            "id": f"cena_{i}",
            "inicio": float(cue.get("start", 0)),
            "fim": float(cue.get("end", 0)),
            "texto": texto_cue,
            "palavras_chave": [],
            "consultas": [],
            "descricao_visual": "",
            "midia": None,
            "status": "pendente",  # pendente | buscando | ok | para_conferir | erro
            "provedor": None,
            "asset_id": None,
            "url_origem": None,
            "licenca": None,
            "autor": None,
        })
    return cenas


def _parse_json_plan(raw: str) -> dict[str, Any] | None:
    """Extrai um objeto JSON do texto devolvido por um provedor LLM."""
    raw = (raw or "").strip()
    first, last = raw.find("{"), raw.rfind("}")
    if first < 0 or last <= first:
        return None
    try:
        value = json.loads(raw[first:last + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    queries = value.get("consultas") or value.get("queries") or []
    if isinstance(queries, str):
        queries = [queries]
    queries = [" ".join(str(q).split())[:100] for q in queries if str(q).strip()]
    keywords = value.get("palavras_chave") or value.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    try:
        motion = max(0, min(100, int(value.get("motion_score", value.get("pontuacao_movimento", 50)))))
    except (TypeError, ValueError):
        motion = 50
    media = str(value.get("recommended_media") or value.get("tipo_midia") or "video").lower()
    media = "image" if media in ("image", "imagem", "foto", "photo") else "video"
    return {
        "palavras_chave": [str(x)[:50] for x in keywords[:6]],
        "consultas": queries[:4],
        "descricao_visual": str(value.get("descricao_visual") or value.get("visual_description") or "")[:400],
        "motion_score": motion,
        "recommended_media": media,
    }


def _openrouter_plan(prompt: str, model: str | None = None) -> dict[str, Any] | None:
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return None
    selected_model = (model or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash").strip()
    if not selected_model:
        selected_model = "google/gemini-2.5-flash"
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-OpenRouter-Title": "Faceless Studio",
        },
        json={
            "model": selected_model,
            "messages": [
                {"role": "system", "content": "Responda somente com JSON válido. Não invente fatos sobre a cena."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.25,
            "max_tokens": 500,
        },
        timeout=(15, 45),
    )
    response.raise_for_status()
    payload = response.json()
    content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    if isinstance(content, list):
        content = " ".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return _parse_json_plan(str(content))


def gerar_consultas_para_cena(
    texto: str,
    idioma: str = "auto",
    max_consultas: int = 4,
    contexto: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    """Gera consultas, descrição e nota de movimento. Prioriza OpenRouter; usa Gemini e texto como fallback."""
    if idioma == "auto":
        idioma = _detect_lang(str(texto or "") + " " + str(contexto or ""))

    lang_instrucao = {
        "pt": "Escreva consultas em português e também em inglês para os bancos stock.",
        "en": "Write the search queries in English only.",
    }.get(idioma, "Escreva consultas em português e também em inglês.")

    contexto_curto = " ".join(str(contexto or "").split())[:2600]
    instrucao = (
        "Você é diretor de fotografia e pesquisador visual de vídeos documentais faceless. "
        "Interprete o significado exato da fala atual, usando os blocos vizinhos somente para resolver pronomes e contexto. "
        "Identifique o assunto principal, a ação que está sendo narrada e o que precisa aparecer visualmente. "
        "A cena deve ilustrar a afirmação atual, não apenas o tema amplo do vídeo nem uma palavra isolada. "
        "Evite resultados genéricos: se a fala descreve alguém comprando um carro usado à vista, não busque apenas luxo, "
        "dinheiro ou carros esportivos; procure a situação concreta descrita. "
        "Devolva APENAS um JSON válido com os campos: "
        "palavras_chave (até 6 itens), consultas (2 a 4 buscas curtas, até 6 palavras cada, com sujeitos/ações/lugares visíveis), "
        "descricao_visual (uma frase concreta), motion_score (inteiro de 0 a 100; alto quando a cena depende de movimento real), "
        "recommended_media (video ou image). "
        "Escolha vídeo para ação, deslocamento, processos em andamento e movimento; escolha imagem para conceitos, retratos, "
        "objetos, mapas, números, lugares estáticos e cenas simbólicas. Não escolha vídeo apenas para preencher. "
        f"{lang_instrucao}\n\n"
        f"CONTEXTO DO ROTEIRO: {contexto_curto or 'Não fornecido'}\n\n"
        f"TRECHO ATUAL: {str(texto)[:1200]}\n\n"
        'Formato: {"palavras_chave":["..."],"consultas":["...","..."],"descricao_visual":"...","motion_score":65,"recommended_media":"video"}'
    )

    # Primeiro tenta OpenRouter. Erros de rede, crédito ou modelo não interrompem o projeto.
    openrouter_error = "OPENROUTER_API_KEY não configurada"
    try:
        plan = _openrouter_plan(instrucao, model=model)
        if plan and plan.get("consultas"):
            plan["consultas"] = plan["consultas"][:max(1, min(4, max_consultas))]
            plan["provider"] = "openrouter"
            return plan
        openrouter_error = "OpenRouter respondeu sem consultas visuais válidas."
    except Exception as exc:
        openrouter_error = str(exc)[:180]

    # Fallback: Gemini, mantendo o mesmo formato editorial.
    chave = _gemini_key()
    if chave:
        corpo = {
            "contents": [{"parts": [{"text": instrucao}]}],
            "generationConfig": {"temperature": 0.35},
        }
        try:
            resp = requests.post(
                f"{API}/models/{TEXT_MODEL}:generateContent",
                headers=_headers(), json=corpo, timeout=(20, 60),
            )
            if resp.ok:
                dados = resp.json()
                partes = ((dados.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                texto_saida = next((parte.get("text", "") for parte in partes if parte.get("text")), "")
                plan = _parse_json_plan(texto_saida)
                if plan and plan.get("consultas"):
                    plan["consultas"] = plan["consultas"][:max(1, min(4, max_consultas))]
                    plan["provider"] = "gemini"
                    plan["fallback_reason"] = openrouter_error
                    return plan
        except Exception:
            pass

    return {
        "palavras_chave": re.findall(r"[A-Za-zÀ-ÿ0-9]+", texto)[:6],
        "consultas": [str(texto)[:80]],
        "descricao_visual": str(texto)[:160],
        "motion_score": 50,
        "recommended_media": "video",
        "provider": "fallback",
    }


def planejar_cenas(srt_text: str, idioma: str = "auto", max_cenas: int = 60,
                   usar_llm: bool = True, max_consultas: int = 4) -> list[dict[str, Any]]:
    """Divide um SRT em cenas e gera consultas de busca para cada uma."""
    cenas = parse_srt_to_cenas(srt_text)
    cenas = cenas[:max_cenas]
    for cena in cenas:
        if usar_llm:
            plano = gerar_consultas_para_cena(cena["texto"], idioma=idioma, max_consultas=max_consultas)
            cena["palavras_chave"] = plano.get("palavras_chave", [])
            consulta_pt = plano.get("consultas", [])
            # Garante pelo menos uma consulta em inglês se o idioma for pt
            if idioma == "pt" and len(consulta_pt) > 0:
                consulta_pt.append(cena["texto"][:60])
            cena["consultas"] = consulta_pt[:max_consultas]
            cena["descricao_visual"] = plano.get("descricao_visual", "")
        else:
            cena["consultas"] = [cena["texto"][:60]]
        cena["status"] = "pendente"
    return cenas


def agrupar_cenas_por_significado(
    srt_text: str,
    *,
    ritmo: str = "balanced",
    idioma: str = "auto",
    extra: str = "",
    max_cenas: int = 120,
    model: str | None = None,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    """Agrupa cues contíguos do SRT por assunto/ação sem alterar texto ou timestamps.

    A IA escolhe somente os limites entre cues. O servidor valida que todos os cues
    aparecem exatamente uma vez, em ordem, e respeita limites de duração/palavras.
    Se OpenRouter falhar ou devolver estrutura inválida, usa o agrupamento temporal
    tradicional; nunca inventa timestamps nem reescreve a legenda.
    """
    cues = parse_srt(str(srt_text or ""))
    language = idioma
    if language == "auto":
        language = _detect_lang(" ".join(c["text"] for c in cues[:80]))
    rule = PACING.get(ritmo, PACING.get("balanced", {"span": 15, "words": 35}))
    max_span = float(rule.get("span", 15))
    max_words = int(rule.get("words", 35))
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        scenes, capped = group_cues(cues, ritmo, language, extra, max_cenas)
        return scenes, capped, {"provider": "temporal_fallback", "reason": "OPENROUTER_API_KEY não configurada", "cues": len(cues)}

    all_groups: list[list[dict[str, Any]]] = []
    chunk_size = 60
    try:
        for offset in range(0, len(cues), chunk_size):
            chunk = cues[offset:offset + chunk_size]
            cue_rows = [
                {"indice": i, "inicio": round(float(c["start"]), 2), "fim": round(float(c["end"]), 2),
                 "fala": str(c["text"])[:260]}
                for i, c in enumerate(chunk)
            ]
            prompt = (
                "Você é editor de documentários faceless. Agrupe legendas consecutivas em CENAS VISUAIS coerentes. "
                "Uma cena deve cobrir uma única ação, situação, local ou ideia visual contínua. "
                "Mude de cena quando o assunto, a ação, o local ou o tempo mudar. "
                "Não crie uma cena para cada legenda curta; junte frases que descrevem a mesma ação. "
                "Nunca misture ações diferentes só para alongar uma cena. "
                f"Idioma do vídeo: {language}. Ritmo: {ritmo}. Duração desejada por cena: até {max_span:.1f} segundos; "
                f"alvo de até {max_words} palavras. Uma pequena exceção é aceitável para preservar uma frase completa. "
                "Responda APENAS JSON válido no formato {\"scene_ends\":[3,7,10]}. "
                "Cada número é o índice zero-based do ÚLTIMO cue de cada cena. "
                "Os limites devem ser crescentes, cobrir todos os cues e terminar exatamente no último índice. "
                "Não altere nem reescreva nenhuma legenda; você está escolhendo apenas os pontos de corte.\n\n"
                f"CUES DO SRT (índice, início/fim em segundos, fala):\n{json.dumps(cue_rows, ensure_ascii=False)}"
            )
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:3000",
                    "X-OpenRouter-Title": "Faceless Studio - Semantic SRT Scenes",
                },
                json={
                    "model": (model or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash").strip(),
                    "messages": [
                        {"role": "system", "content": "Agrupe cues por continuidade visual. Responda somente JSON válido."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1200,
                },
                timeout=(15, 60),
            )
            response.raise_for_status()
            payload = response.json()
            raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            if isinstance(raw, list):
                raw = " ".join(str(part.get("text") or "") for part in raw if isinstance(part, dict))
            first, last = str(raw).find("{"), str(raw).rfind("}")
            if first < 0 or last <= first:
                raise ValueError("OpenRouter não devolveu JSON de agrupamento válido.")
            data = json.loads(str(raw)[first:last + 1])
            ends = data.get("scene_ends") or data.get("fim_cenas") or []
            if not isinstance(ends, list) or not ends:
                raise ValueError("OpenRouter não devolveu limites de cenas.")
            normalized = [int(value) for value in ends]
            if normalized != sorted(set(normalized)) or normalized[-1] != len(chunk) - 1:
                raise ValueError("Os limites não cobrem todos os cues em ordem.")
            start = 0
            chunk_groups: list[list[dict[str, Any]]] = []
            for end in normalized:
                if end < start or end >= len(chunk):
                    raise ValueError("Limite de cena fora do SRT.")
                group = chunk[start:end + 1]
                words = sum(len(str(c["text"]).split()) for c in group)
                span = float(group[-1]["end"]) - float(group[0]["start"])
                if span > max_span * 1.6 or words > max_words * 1.6:
                    raise ValueError("Agrupamento ultrapassou o limite de segurança do ritmo.")
                chunk_groups.append(group)
                start = end + 1
            if start != len(chunk):
                raise ValueError("Há legendas sem cena atribuída.")
            all_groups.extend(chunk_groups)
    except Exception as exc:
        scenes, capped = group_cues(cues, ritmo, language, extra, max_cenas)
        return scenes, capped, {
            "provider": "temporal_fallback",
            "reason": f"Agrupamento semântico indisponível: {str(exc)[:180]}",
            "cues": len(cues),
        }

    if len(all_groups) > max(1, int(max_cenas)):
        scenes, capped = group_cues(cues, ritmo, language, extra, max_cenas)
        return scenes, capped, {
            "provider": "temporal_fallback",
            "reason": "O agrupamento semântico excedeu o limite de cenas; aplicado agrupamento seguro.",
            "cues": len(cues),
        }
    scenes = [_scene(group, index + 1, language, extra) for index, group in enumerate(all_groups)]
    return scenes, False, {
        "provider": "openrouter",
        "model": (model or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash").strip(),
        "cues": len(cues),
        "scenes": len(scenes),
    }


def ritmo_para_duracao(ritmo: str) -> tuple[float, float]:
    """Devolve (min, max) segundos para cada ritmo de cena."""
    tabelas = {
        "ultra_rapido": (2, 4),
        "rapido": (3, 8),
        "normal": (8, 15),
        "lento": (15, 30),
        "muito_lento": (30, 60),
        "automatico": (5, 15),
    }
    return tabelas.get(ritmo, tabelas["rapido"])
