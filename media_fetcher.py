"""Interface MediaFetcher — aquisição de arquivo de mídia.

Implementação concreta é decisão do dono do projeto (registrado em docs/decisoes.md).
Não contornamos proteções nem termos de uso do YouTube.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from providers_base import MediaFetcher


class YtDlpFetcher(MediaFetcher):
    """Fetch via yt-dlp (se disponível). Apenas URLs informadas pelo usuário."""

    name = "yt_dlp"

    async def fetch(self, url: str, dest_dir: str | None = None) -> dict[str, Any]:
        import subprocess
        import json as _json
        dest = Path(dest_dir or "data/downloads")
        dest.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(dest / "%(id)s.%(ext)s")
        cmd = ["yt-dlp", "--print-json", "-o", out_tmpl, url]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0:
                raise RuntimeError(f"yt-dlp falhou: {proc.stderr[-500:]}")
            info = _json.loads(proc.stdout.splitlines()[-1])
            path = Path(info.get("_filename", ""))
            return {
                "path": str(path),
                "filename": path.name,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else 0,
                "duration": info.get("duration", 0.0),
                "url_origem": url,
            }
        except FileNotFoundError:
            raise RuntimeError("yt-dlp não está instalado. O download de clipes do YouTube requer yt-dlp.")
        except Exception as exc:
            raise RuntimeError(str(exc))

    def public_meta(self) -> dict[str, Any]:
        return {"id": self.name, "needs_key": False, "ready": True}


class ManualFetcher(MediaFetcher):
    """Fetch manual: o usuário já enviou o arquivo. Apenas registra o caminho."""

    name = "manual"

    async def fetch(self, url: str, dest_dir: str | None = None) -> dict[str, Any]:
        path = Path(url)
        if not path.exists():
            raise RuntimeError(f"Arquivo não encontrado: {url}")
        return {
            "path": str(path),
            "filename": path.name,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "duration": 0.0,
            "url_origem": url,
        }

    def public_meta(self) -> dict[str, Any]:
        return {"id": self.name, "needs_key": False, "ready": True}


FETCHERS: list[MediaFetcher] = [YtDlpFetcher(), ManualFetcher()]


def get_fetcher(name: str) -> MediaFetcher | None:
    for f in FETCHERS:
        if f.name == name:
            return f
    return None
