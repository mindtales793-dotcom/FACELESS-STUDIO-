"""Verificação semântica de mídia por bloco do SRT usando OpenRouter multimodal.

A IA compara a fala, o contexto editorial, os metadados e as miniaturas dos resultados.
Só candidatos acima do limite são aprovados quando a checagem visual é concluída.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"
MAX_CANDIDATES = 8
DEFAULT_MIN_SCORE = 68


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(
            str(part.get("text") or "")
            for part in value
            if isinstance(part, dict) and part.get("text")
        )
    return str(value or "")


def _parse_results(raw: str) -> list[dict[str, Any]]:
    raw = (raw or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        payload = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("resultados") or payload.get("results") or payload.get("candidates") or []
    if isinstance(items, dict):
        items = list(items.values())
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("indice", item.get("index", item.get("candidate_index"))))
            score = max(0, min(100, int(float(item.get("nota", item.get("score", item.get("compatibilidade", 0)))))))
        except (TypeError, ValueError):
            continue
        reason = str(item.get("motivo") or item.get("reason") or item.get("explicacao") or "").strip()[:280]
        out.append({"index": index, "score": score, "reason": reason})
    return out


def verify_scene_candidates(
    *,
    scene_text: str,
    visual_description: str = "",
    context: str = "",
    candidates: list[dict[str, Any]] | None = None,
    model: str | None = None,
    min_score: int = DEFAULT_MIN_SCORE,
    disable_openrouter: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Retorna somente prévias compatíveis após uma resposta válida do OpenRouter.

    Se a API estiver indisponível, mantém os resultados e marca a verificação como
    indisponível; isso evita quebrar a busca, mas não finge que houve validação.
    """
    items = [dict(item) for item in (candidates or []) if isinstance(item, dict)]
    threshold = max(50, min(95, int(min_score or DEFAULT_MIN_SCORE)))
    if not items:
        return [], {"status": "empty", "checked": 0, "accepted": 0, "rejected": 0, "threshold": threshold}

    if disable_openrouter:
        return items, {
            "status": "unavailable", "checked": 0, "accepted": len(items), "rejected": 0,
            "threshold": threshold, "quota_exhausted": True,
            "message": "Verificação visual do OpenRouter pausada nesta busca após HTTP 402; prévias mantidas sem validação por IA.",
        }

    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return items, {
            "status": "unavailable", "checked": 0, "accepted": len(items), "rejected": 0,
            "threshold": threshold, "message": "Configure OPENROUTER_API_KEY para conferir as prévias com visão.",
        }

    selected_model = (model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    indexed = []
    for index, item in enumerate(items[:MAX_CANDIDATES]):
        thumbnail = str(item.get("thumbnail") or "").strip()
        if thumbnail.startswith(("https://", "http://")):
            indexed.append((index, item, thumbnail))
    if not indexed:
        return items, {
            "status": "unavailable", "checked": 0, "accepted": len(items), "rejected": 0,
            "threshold": threshold, "message": "Os resultados não forneceram miniaturas acessíveis para análise visual.",
        }

    metadata = []
    for index, item, _ in indexed:
        metadata.append({
            "indice": index,
            "provedor": str(item.get("provider") or "")[:70],
            "tipo": str(item.get("media_type") or "")[:20],
            "titulo": str(item.get("title") or "")[:180],
            "descricao": str(item.get("description") or "")[:240],
            "tags": item.get("tags") or [],
            "duracao_segundos": item.get("duration"),
        })

    prompt = (
        "Você é um verificador rigoroso de continuidade visual para um vídeo narrado. "
        "Compare cada prévia numerada com o BLOCO EXATO da narração e com a descrição visual. "
        "O contexto geral serve apenas para desambiguar; a fala atual tem prioridade. "
        "Não aprove algo só porque compartilha uma palavra ou o tema amplo. "
        "Verifique se o assunto, a ação e o ambiente visíveis realmente apoiam o que está sendo dito. "
        "Se a imagem for genérica, ambígua, promocional ou mostrar outro assunto, dê nota baixa. "
        "A miniatura é apenas uma prévia e não prova todos os quadros do vídeo; avalie somente o que ela e os metadados permitem afirmar. "
        f"Aprove somente notas iguais ou superiores a {threshold}. "
        "Responda APENAS JSON válido no formato "
        '{"resultados":[{"indice":0,"nota":90,"motivo":"explicação curta"}]}. '
        "Use exatamente os índices fornecidos; inclua uma avaliação para cada candidato apresentado.\n\n"
        f"CONTEXTO DO ROTEIRO E BLOCOS VIZINHOS:\n{str(context or '')[:3600]}\n\n"
        f"BLOCO EXATO DA NARRAÇÃO:\n{str(scene_text or '')[:1400]}\n\n"
        f"DESCRIÇÃO VISUAL ESPERADA:\n{str(visual_description or '')[:500]}\n\n"
        f"METADADOS DOS CANDIDATOS (índices originais zero-based):\n{json.dumps(metadata, ensure_ascii=False)}"
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for index, _, thumbnail in indexed:
        content.append({"type": "text", "text": f"PRÉVIA VISUAL DO CANDIDATO índice {index}:"})
        content.append({"type": "image_url", "image_url": {"url": thumbnail}})

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3000",
                "X-OpenRouter-Title": "Faceless Studio - Semantic Media Check",
            },
            json={
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": "Avalie evidências visuais com rigor. Responda somente JSON válido."},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.1,
                "max_tokens": 900,
            },
            timeout=(15, 60),
        )
        response.raise_for_status()
        payload = response.json()
        raw = _content_text((((payload.get("choices") or [{}])[0].get("message") or {}).get("content")))
        scored = _parse_results(raw)
    except Exception as exc:
        response_error = getattr(exc, "response", None)
        status_code = getattr(response_error, "status_code", None)
        error_text = str(exc).lower()
        quota_exhausted = status_code == 402 or "402" in error_text or "payment required" in error_text
        message = (
            "HTTP 402 Payment Required: saldo ou limite de créditos do OpenRouter insuficiente."
            if quota_exhausted
            else f"OpenRouter não conseguiu conferir as prévias: {str(exc)[:180]}"
        )
        return items, {
            "status": "unavailable", "checked": 0, "accepted": len(items), "rejected": 0,
            "threshold": threshold, "message": message, "quota_exhausted": quota_exhausted,
        }

    known_indices = {index for index, _, _ in indexed}
    score_by_index = {entry["index"]: entry for entry in scored if entry["index"] in known_indices}
    if not score_by_index:
        return items, {
            "status": "unavailable", "checked": 0, "accepted": len(items), "rejected": 0,
            "threshold": threshold, "message": "O modelo não devolveu notas válidas para as prévias.",
        }

    accepted = []
    for index, item in enumerate(items):
        result = score_by_index.get(index)
        if result:
            item["media_match_score"] = result["score"]
            item["media_match_reason"] = result["reason"] or "Compatibilidade avaliada pela IA."
            item["relevance_verified"] = True
            item["media_match_status"] = "approved" if result["score"] >= threshold else "rejected"
            item["media_match_model"] = selected_model
            if result["score"] >= threshold:
                accepted.append(item)
        else:
            item["relevance_verified"] = False
            item["media_match_status"] = "not_checked"
            item["media_match_reason"] = "A IA não conseguiu avaliar esta prévia."
    accepted.sort(
        key=lambda item: (
            int(item.get("media_match_score") or 0),
            float(item.get("rank") or 0),
        ),
        reverse=True,
    )
    return accepted, {
        "status": "verified",
        "checked": len(score_by_index),
        "accepted": len(accepted),
        "rejected": len(items) - len(accepted),
        "threshold": threshold,
        "model": selected_model,
    }
