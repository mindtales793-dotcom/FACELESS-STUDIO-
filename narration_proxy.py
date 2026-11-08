"""
Proxy para o servidor de narração DarkCut (Node.js/Express).

Este módulo encaminha requisições de narração do FastAPI (Python)
para o servidor Node.js rodando na porta 3115.

Uso:
    from narration_proxy import create_narration, get_narration_status, ...
"""

from __future__ import annotations

import httpx
import uuid
from typing import Any, Dict, Optional
from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse

NARRATION_BASE_URL = "http://127.0.0.1:3115"

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=NARRATION_BASE_URL, timeout=httpx.Timeout(30.0))
    return _client


async def create_narration_proxy(
    text: str,
    reference_id: str | None,
    model: str = "s2.1-pro-free",
    speed: float = 1.0,
    stability: float = 0.5,
    expressiveness: float = 0.5,
    max_concurrent: int = 4,
) -> Dict[str, Any]:
    """Encaminha criação de narração para o serviço Node.js."""
    client = _get_client()
    try:
        resp = await client.post(
            "/api/narration/generate",
            json={
                "text": text,
                "referenceId": reference_id,
                "model": model,
                "format": "mp3",
                "concurrency": max_concurrent,
            },
        )
        if resp.status_code >= 400:
            detail = resp.text or "Erro ao criar narração"
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Servidor de narração não está disponível. Inicie o server-narration.js na porta 3115. Erro: {exc}",
        )


async def get_narration_status_proxy(job_id: str) -> Dict[str, Any]:
    """Consulta o status de um job de narração."""
    client = _get_client()
    try:
        resp = await client.get(f"/api/narration/{job_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Trabalho de narração não encontrado.")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text or "Erro ao consultar status.")
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Servidor de narração não está disponível. Erro: {exc}",
        )


async def cancel_narration_proxy(job_id: str) -> Dict[str, Any]:
    """Cancela um job de narração."""
    client = _get_client()
    try:
        resp = await client.delete(f"/api/narration/{job_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Trabalho de narração não encontrado.")
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Servidor de narração não está disponível. Erro: {exc}",
        )


async def download_narration_proxy(job_id: str):
    """Baixa o áudio final de um job de narração."""
    client = _get_client()
    try:
        resp = await client.get(f"/api/narration/{job_id}/download", follow_redirects=True)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Áudio não encontrado.")
        if resp.status_code == 409:
            raise HTTPException(status_code=409, detail="A narração ainda não está pronta.")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text or "Erro ao baixar áudio.")

        # Retorna StreamingResponse com o conteúdo do áudio
        return StreamingResponse(
            resp.aiter_bytes(),
            media_type=resp.headers.get("content-type", "audio/mpeg"),
            headers={
                "Content-Disposition": resp.headers.get(
                    "content-disposition", 'attachment; filename="narracao.mp3"'
                ),
            },
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Servidor de narração não está disponível. Erro: {exc}",
        )


async def get_narration_health_proxy() -> Dict[str, Any]:
    """Consulta a saúde do serviço de narração."""
    client = _get_client()
    try:
        resp = await client.get("/api/narration/health")
        if resp.status_code >= 400:
            return {"ok": False, "service": "darkcut-narration", "error": resp.text}
        return resp.json()
    except httpx.RequestError:
        return {"ok": False, "service": "darkcut-narration", "error": "Servidor não disponível"}


async def close_client() -> None:
    """Fecha o cliente HTTP (chame ao encerrar o app)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
