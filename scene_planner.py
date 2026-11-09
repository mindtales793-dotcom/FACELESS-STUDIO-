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


def gerar_consultas_para_cena(texto: str, idioma: str = "auto", max_consultas: int = 4) -> dict[str, Any]:
    """Usa LLM para gerar 2–4 consultas de busca curtas + descrição visual de uma cena."""
    if idioma == "auto":
        idioma = _detect_lang(texto)

    lang_instrucao = {
        "pt": "Escreva as consultas em português e em inglês.",
        "en": "Write the queries in English only.",
    }.get(idioma, "Escreva as consultas em português e em inglês.")

    instrucao = (
        "Você é um roteirista de documentário de canal dark/animação 2D. "
        "Leia este trecho de narração com timestamp e devolva APENAS um JSON válido com:\n"
        "- palavras_chave: até 6 palavras-chave do trecho\n"
        "- consultas: lista de 2 a 4 consultas de busca curtas (máximo 6 palavras cada) para encontrar imagens/vídeos de banco "
        "ou gerar com IA. Use termos visuais concretos.\n"
        "- descricao_visual: uma frase descrevendo o que deve aparecer na imagem/vídeo desta cena\n"
        f"{lang_instrucao}\n\n"
        f'Trecho: "{texto}"\n\n'
        'Exemplo de saída:\n'
        '{"palavras_chave": ["buraco negro", "espaço", "escuridão"], '
        '"consultas": ["black hole space", "buraco negro universo", "cosmic darkness"], '
        '"descricao_visual": "Um buraco negro no centro de uma galáxia escura com disco de acreção brilhando"}'
    )

    chave = _gemini_key()
    if not chave:
        # Fallback sem LLM: usa o texto como consulta
        return {
            "palavras_chave": texto.split()[:6],
            "consultas": [texto[:60]],
            "descricao_visual": texto[:120],
        }

    corpo = {
        "contents": [{"parts": [{"text": instrucao}]}],
        "generationConfig": {"temperature": 0.4},
    }
    try:
        resp = requests.post(f"{API}/models/{IMAGE_MODEL}:generateContent", headers=_headers(), json=corpo, timeout=(20, 60))
        if resp.ok:
            dados = resp.json()
            partes = ((dados.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            texto_saida = ""
            for parte in partes:
                if parte.get("text"):
                    texto_saida = parte["text"].strip()
                    break
            # Tenta extrair JSON
            inicio = texto_saida.find("{")
            fim = texto_saida.rfind("}")
            if inicio != -1 and fim != -1:
                bloco = texto_saida[inicio:fim + 1]
                return json.loads(bloco)
    except Exception:
        pass
    return {
        "palavras_chave": texto.split()[:6],
        "consultas": [texto[:60]],
        "descricao_visual": texto[:120],
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
