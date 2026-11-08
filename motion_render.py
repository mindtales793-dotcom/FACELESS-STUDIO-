"""Renderização de cenas com Remotion (Node.js) para o Faceless Cloud Studio."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from store import DATA_DIR, now_iso, lock, ffmpeg_path

MOTION_DIR = DATA_DIR / "motion"
MOTION_DIR.mkdir(parents=True, exist_ok=True)

REMOTION_DIR = Path(__file__).resolve().parent / "remotion"
RENDER_SCRIPT = REMOTION_DIR / "render.js"


def _cache_key(props: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(props, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def render_scene(
    text: str,
    duration: float = 5.0,
    width: int = 1920,
    height: int = 1080,
    cor_primaria: str = "#2F6FED",
    estilo: str = "documentario",
) -> dict[str, Any]:
    """Renderiza uma cena com Remotion e retorna {url, path, cache_hit, duration_s}."""
    props = {
        "text": text,
        "duration": duration,
        "width": width,
        "height": height,
        "cor_primaria": cor_primaria,
        "estilo": estilo,
    }
    chave = _cache_key(props)
    out_path = MOTION_DIR / f"{chave}.mp4"
    meta_path = MOTION_DIR / f"{chave}.json"

    if out_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return {
            "url": f"/api/motion/{chave}.mp4",
            "path": str(out_path),
            "cache_hit": True,
            "duration_s": duration,
        }

    # Grava props em JSON temporário para o Node.js ler
    props_file = MOTION_DIR / f"{chave}.props.json"
    with lock:
        props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    try:
        node_cmd = ["node", str(RENDER_SCRIPT), str(props_file), str(out_path), ffmpeg_path()]
        result = subprocess.run(
            node_cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(REMOTION_DIR),
        )

        # Lê saída JSON do node (pode estar no stdout ou stderr se houver logs do ffmpeg)
        stdout_lines = result.stdout.strip().splitlines()
        stderr_lines = result.stderr.strip().splitlines()

        render_result = None
        # Tenta encontrar JSON no stdout
        for line in reversed(stdout_lines):
            try:
                render_result = json.loads(line)
                break
            except Exception:
                continue
        # Se não achou no stdout, tenta no stderr
        if render_result is None:
            for line in reversed(stderr_lines):
                try:
                    render_result = json.loads(line)
                    break
                except Exception:
                    continue

        if render_result is None:
            render_result = {"ok": True, "output": str(out_path)}

        if not render_result.get("ok") and not out_path.exists():
            raise RuntimeError(f"Remotion não gerou saída: {(result.stdout + result.stderr)[:500]}")

        # Se o arquivo existe, considera sucesso independente do returncode
        if not out_path.exists():
            raise RuntimeError(f"Arquivo de saída não foi gerado: {(result.stdout + result.stderr)[:500]}")

        meta = {
            "tipo_cena": "faceless_scene",
            "estilo": estilo,
            "cor_primaria": cor_primaria,
            "duration_s": duration,
            "criado_em": now_iso(),
            "text": text,
        }
        with lock:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        props_file.unlink(missing_ok=True)

        return {
            "url": f"/api/motion/{chave}.mp4",
            "path": str(out_path),
            "cache_hit": False,
            "duration_s": duration,
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError("Remotion render excedeu o tempo limite (180s).")
    except Exception as exc:
        raise RuntimeError(f"Erro ao renderizar cena Remotion: {exc}")
