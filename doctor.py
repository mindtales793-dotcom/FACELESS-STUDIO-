"""Diagnóstico local e seguro das dependências do Faceless Studio.

Não executa instalações, não envia chaves pela rede e nunca devolve o conteúdo
de variáveis de ambiente. Apenas consulta o estado da máquina e do projeto.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from store import BASE_DIR, DATA_DIR, ffmpeg_path


def _version(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=8, check=False
        )
        output = (result.stdout or result.stderr or "").strip().splitlines()
        if result.returncode == 0 and output:
            return True, output[0][:180]
        detail = output[0][:180] if output else f"código {result.returncode}"
        return False, detail
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)[:180]


def _resolve_ffprobe(ffmpeg: str | None) -> str | None:
    candidates: list[str] = []
    if ffmpeg:
        path = Path(ffmpeg)
        candidates.extend([
            str(path.with_name("ffprobe.exe" if path.suffix.lower() == ".exe" else "ffprobe")),
            str(path.with_name("ffprobe")),
        ])
    found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if found:
        candidates.append(found)
    return next((item for item in candidates if Path(item).is_file()), None)


def run_diagnostics() -> dict[str, Any]:
    """Executa verificações rápidas e devolve somente informações não secretas."""
    checks: list[dict[str, Any]] = []

    def add(check_id: str, label: str, status: str, detail: str, required: bool = False) -> None:
        checks.append({
            "id": check_id,
            "label": label,
            "status": status,
            "detail": detail[:240],
            "required": required,
        })

    # Python e dependências essenciais do servidor.
    py_ok = sys.version_info >= (3, 11)
    add(
        "python", "Python",
        "ok" if py_ok else "error",
        f"{sys.version.split()[0]} · recomendado Python 3.11 ou superior",
        required=True,
    )
    modules = {
        "fastapi": "FastAPI",
        "uvicorn": "Uvicorn",
        "requests": "Requests",
        "pydantic": "Pydantic",
        "yt_dlp": "yt-dlp",
        "httpx": "HTTPX",
    }
    missing = [label for module, label in modules.items() if importlib.util.find_spec(module) is None]
    add(
        "python-deps", "Dependências Python",
        "error" if missing else "ok",
        "Ausentes: " + ", ".join(missing) if missing else "Dependências principais encontradas",
        required=True,
    )

    # FFmpeg e FFprobe são necessários para validar mídia e exportar vídeos.
    try:
        configured_ffmpeg = str(ffmpeg_path() or "").strip()
    except Exception:
        # ffmpeg_path() lança RuntimeError quando o executável não está instalado.
        configured_ffmpeg = ""
    ffmpeg = configured_ffmpeg if configured_ffmpeg and Path(configured_ffmpeg).is_file() else (
        shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    )
    if ffmpeg:
        ok, detail = _version([ffmpeg, "-version"])
        add("ffmpeg", "FFmpeg", "ok" if ok else "error", detail if ok else f"Executável encontrado, mas não iniciou: {detail}", True)
    else:
        add("ffmpeg", "FFmpeg", "error", "Não encontrado no PATH. Instale o FFmpeg e reinicie o estúdio.", True)

    ffprobe = _resolve_ffprobe(ffmpeg)
    if ffprobe:
        ok, detail = _version([ffprobe, "-version"])
        add("ffprobe", "FFprobe", "ok" if ok else "error", detail if ok else f"Executável encontrado, mas não iniciou: {detail}", True)
    else:
        add("ffprobe", "FFprobe", "error", "Não encontrado. O FFprobe acompanha a distribuição completa do FFmpeg.", True)

    # Node/Remotion são necessários somente para as cenas animadas Remotion.
    node = shutil.which("node") or shutil.which("node.exe")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if node:
        ok, detail = _version([node, "--version"])
        add("node", "Node.js", "ok" if ok else "warning", detail if ok else f"Node encontrado, mas não iniciou: {detail}")
    else:
        add("node", "Node.js", "warning", "Não encontrado. Necessário para renderizar cenas com Remotion.")
    if npm:
        ok, detail = _version([npm, "--version"])
        add("npm", "npm", "ok" if ok else "warning", detail if ok else f"npm não iniciou: {detail}")
    else:
        add("npm", "npm", "warning", "Não encontrado. Necessário para instalar dependências do Remotion.")

    remotion_dir = BASE_DIR / "remotion"
    renderer_pkg = remotion_dir / "node_modules" / "@remotion" / "renderer" / "package.json"
    remotion_pkg = remotion_dir / "node_modules" / "remotion" / "package.json"
    remotion_ready = renderer_pkg.is_file() and remotion_pkg.is_file()
    add(
        "remotion", "Dependências Remotion",
        "ok" if remotion_ready else "warning",
        "Dependências instaladas" if remotion_ready else "Ainda não instaladas. Execute INSTALAR_REMOTION_WINDOWS.bat se for usar cenas animadas.",
    )

    # Diretório de dados precisa permitir gravações e ter espaço razoável.
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="doctor_", dir=DATA_DIR, delete=True):
            pass
        free_gb = shutil.disk_usage(DATA_DIR).free / (1024 ** 3)
        status = "ok" if free_gb >= 1 else "warning"
        add("storage", "Pasta de dados e espaço", status, f"Gravação permitida · {free_gb:.1f} GB livres")
    except OSError as exc:
        add("storage", "Pasta de dados e espaço", "error", f"Sem permissão de gravação: {exc}", True)

    # Confere apenas se as chaves estão configuradas; seus valores nunca são retornados.
    try:
        import keys_mgr
        configured = [item for item in keys_mgr.get_all_keys_status() if item.get("configured")]
        add("api-keys", "Chaves de API", "ok" if configured else "warning",
            f"{len(configured)} credencial(is) configurada(s). Os valores não são exibidos.")
    except Exception:
        add("api-keys", "Chaves de API", "warning", "Não foi possível consultar o estado das credenciais.")

    errors = sum(1 for item in checks if item["status"] == "error" and item["required"])
    warnings = sum(1 for item in checks if item["status"] == "warning")
    return {
        "ok": errors == 0,
        "summary": "Sistema pronto para as verificações essenciais." if errors == 0 else f"{errors} verificação(ões) essencial(is) precisam de atenção.",
        "counts": {
            "ok": sum(1 for item in checks if item["status"] == "ok"),
            "warning": warnings,
            "error": sum(1 for item in checks if item["status"] == "error"),
        },
        "checks": checks,
    }
