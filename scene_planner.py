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

from scenes import parse_srt

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
        idioma = _detect_lang(texto)

    lang_instrucao = {
        "pt": "Escreva consultas em português e também em inglês para os bancos stock.",
        "en": "Write the search queries in English only.",
    }.get(idioma, "Escreva consultas em português e também em inglês.")

    contexto_curto = " ".join(str(contexto or "").split())[:2600]
    instrucao = (
        "Você é diretor de fotografia e pesquisador visual de vídeos documentais faceless. "
        "Entenda o trecho isoladamente e também o contexto do roteiro. Crie termos que encontrem imagens "
        "ou vídeos realmente relacionados à ideia, não apenas palavras soltas do texto. "
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
    try:
        plan = _openrouter_plan(instrucao, model=model)
        if plan and plan.get("consultas"):
            plan["consultas"] = plan["consultas"][:max(1, min(4, max_consultas))]
            plan["provider"] = "openrouter"
            return plan
    except Exception:
        pass

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
