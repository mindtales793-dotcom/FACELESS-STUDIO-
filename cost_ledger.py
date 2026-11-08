"""Ledger de custos — registra cada chamada paga.

Grava {projeto, etapa, provedor, modelo, unidades, custo_estimado, timestamp}.
Usado na aba Gastos e para exportação CSV.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from store import DATA_DIR, now_iso

COSTS_DIR = DATA_DIR / "costs"
COSTS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_cost(project_id: str | None, etapa: str, provedor: str, modelo: str,
                  unidades: float, custo_estimado: float, moeda: str = "USD",
                  metadata: dict[str, Any] | None = None) -> str:
    """Registra um custo no ledger. Devolve o id do registro."""
    import uuid
    record_id = uuid.uuid4().hex
    record = {
        "id": record_id,
        "project_id": project_id,
        "etapa": etapa,
        "provedor": provedor,
        "modelo": modelo,
        "unidades": unidades,
        "custo_estimado": round(custo_estimado, 6),
        "moeda": moeda,
        "timestamp": _now(),
        "metadata": metadata or {},
    }
    path = COSTS_DIR / f"{record_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record_id


def list_costs(project_id: str | None = None, etapa: str | None = None,
               provedor: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for p in COSTS_DIR.iterdir():
        if not p.is_file() or p.suffix != ".json":
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if project_id and rec.get("project_id") != project_id:
            continue
        if etapa and rec.get("etapa") != etapa:
            continue
        if provedor and rec.get("provedor") != provedor:
            continue
        records.append(rec)
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[:limit]


def total_costs(project_id: str | None = None) -> dict[str, Any]:
    records = list_costs(project_id=project_id, limit=10000)
    total = sum(r.get("custo_estimado", 0) for r in records)
    por_provedor: dict[str, float] = {}
    por_etapa: dict[str, float] = {}
    for r in records:
        p = r.get("provedor", "desconhecido")
        e = r.get("etapa", "desconhecida")
        por_provedor[p] = round(por_provedor.get(p, 0) + r.get("custo_estimado", 0), 6)
        por_etapa[e] = round(por_etapa.get(e, 0) + r.get("custo_estimado", 0), 6)
    return {
        "total": round(total, 6),
        "moeda": "USD",
        "quantidade": len(records),
        "por_provedor": por_provedor,
        "por_etapa": por_etapa,
    }
