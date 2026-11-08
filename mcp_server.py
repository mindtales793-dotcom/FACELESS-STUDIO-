"""Servidor MCP do Faceless Cloud Studio.

Expõe a geração de imagem/vídeo do "Google Flow" (modelos Nano Banana e Veo, via Gemini API)
e o estado dos projetos do estúdio para qualquer cliente MCP (Claude Desktop, Claude Code...).

Rodar:  python mcp_server.py            (stdio)
Config Claude Desktop / Claude Code:
  {"mcpServers": {"faceless-studio": {"command": "python", "args": ["/caminho/mcp_server.py"],
                  "env": {"GEMINI_API_KEY": "...", "DATA_DIR": "/caminho/data"}}}}

Observação: o Google Flow não tem API pública; aqui usamos os mesmos modelos pela Gemini API.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import flow
from store import DATA_DIR, read_state

mcp = FastMCP("faceless-studio")
OUT = DATA_DIR / "mcp_outputs"
OUT.mkdir(parents=True, exist_ok=True)


def _dest(ext: str) -> Path:
    return OUT / f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.{ext}"


@mcp.tool()
def flow_status() -> dict:
    """Mostra se a GEMINI_API_KEY está configurada e quais modelos de imagem e vídeo serão usados."""
    return {"ready": flow.is_ready(), "image_model": flow.IMAGE_MODEL, "video_model": flow.VIDEO_MODEL}


@mcp.tool()
def flow_generate_image(prompt: str, ratio: str = "16:9") -> str:
    """Gera uma imagem (Nano Banana). ratio: 16:9, 9:16 ou 1:1. Devolve o caminho do arquivo salvo."""
    return str(flow.generate_image(prompt, ratio, _dest("png")))


@mcp.tool()
def flow_generate_video(prompt: str, ratio: str = "16:9", seconds: int = 6) -> str:
    """Gera um clipe de vídeo (Veo). seconds: 4, 6 ou 8. Demora alguns minutos e é cobrado na sua chave."""
    return str(flow.generate_video(prompt, ratio, seconds, _dest("mp4")))


@mcp.tool()
def list_studio_projects() -> list[dict]:
    """Lista os projetos do estúdio com status e progresso."""
    rows = []
    for p in sorted(DATA_DIR.glob("*/project.json")):
        try:
            s = read_state(p.parent.name)
        except Exception:
            continue
        rows.append({"id": p.parent.name, "title": s.get("title"), "status": s.get("status"), "progress": s.get("progress")})
    return rows


@mcp.tool()
def studio_project_status(project_id: str) -> dict:
    """Etapa atual, progresso e as últimas linhas do registro de um projeto."""
    s = read_state(project_id)
    return {"status": s.get("status"), "progress": s.get("progress"), "stage": s.get("current_stage"),
            "message": s.get("message"), "error": s.get("error"), "log": [l["msg"] for l in s.get("log", [])[-10:]]}


if __name__ == "__main__":
    mcp.run()
