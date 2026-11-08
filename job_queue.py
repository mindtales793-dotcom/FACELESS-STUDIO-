"""Fila assíncrona de jobs com retry e backoff exponencial.

Persiste estado em `data/jobs/`. Cada job tem: id, etapa, projeto, status,
progresso, tentativas, erro, resultado. Uma etapa que falha não derruba o
projeto inteiro.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from store import DATA_DIR, now_iso

JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = int(os.getenv("JOB_MAX_RETRIES", "3"))
BACKOFF_BASE = float(os.getenv("JOB_BACKOFF_BASE", "2"))  # segundos


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(etapa: str, project_id: str | None = None, payload: dict[str, Any] | None = None) -> str:
    """Cria um job na fila e devolve o id."""
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "etapa": etapa,
        "project_id": project_id,
        "status": "queued",          # queued | running | ok | erro | pulada
        "progresso": 0,
        "tentativas": 0,
        "max_retries": MAX_RETRIES,
        "erro": None,
        "resultado": None,
        "payload": payload or {},
        "criado_em": _now(),
        "atualizado_em": _now(),
        "iniciado_em": None,
        "finalizado_em": None,
    }
    _write(job)
    return job_id


def _write(job: dict[str, Any]) -> None:
    path = _job_path(job["id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def read_job(job_id: str) -> dict[str, Any] | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def update_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    job = read_job(job_id)
    if not job:
        return None
    job.update(fields)
    job["atualizado_em"] = _now()
    _write(job)
    return job


def list_jobs(project_id: str | None = None, etapa: str | None = None,
              status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for p in JOBS_DIR.iterdir():
        if not p.is_file() or p.suffix != ".json":
            continue
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if project_id and job.get("project_id") != project_id:
            continue
        if etapa and job.get("etapa") != etapa:
            continue
        if status and job.get("status") != status:
            continue
        jobs.append(job)
    jobs.sort(key=lambda j: j.get("criado_em", ""), reverse=True)
    return jobs[:limit]


async def run_job(job_id: str, handler: Callable[[dict[str, Any]], Any],
                  *, on_progress: Callable[[float], None] | None = None) -> None:
    """Executa um job com retry e backoff exponencial.

    `handler` recebe o job e deve devolver o resultado ou lançar exceção.
    """
    job = read_job(job_id)
    if not job:
        return
    update_job(job_id, status="running", iniciado_em=_now(), progresso=5)

    last_exc: Exception | None = None
    for tentativa in range(1, job.get("max_retries", MAX_RETRIES) + 1):
        try:
            update_job(job_id, tentativas=tentativa,
                       detail=f"Tentativa {tentativa}/{job.get('max_retries', MAX_RETRIES)}")
            resultado = await handler(job)
            update_job(job_id, status="ok", progresso=100,
                       finalizado_em=_now(), resultado=resultado, erro=None)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc)[:300]
            update_job(job_id, erro=msg, detail=f"Erro na tentativa {tentativa}: {msg}")
            if tentativa < job.get("max_retries", MAX_RETRIES):
                espera = BACKOFF_BASE ** tentativa
                await asyncio.sleep(espera)
            else:
                update_job(job_id, status="erro", finalizado_em=_now(),
                           erro=f"Falhou após {job.get('max_retries', MAX_RETRIES)} tentativas: {msg}")
