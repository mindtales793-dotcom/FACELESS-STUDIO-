"""Estado dos projetos, rastreador de etapas (o "robô") e utilitários de mídia."""
from __future__ import annotations

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file() -> None:
    """Lê o arquivo .env ao lado do app (sem sobrescrever variáveis já definidas)."""
    env = BASE_DIR / ".env"
    if not env.exists():
        return
    for raw in env.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR = DATA_DIR / "library" / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR = DATA_DIR / "preview_cache"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

MAX_MEDIA_MB = int(os.getenv("MAX_MEDIA_MB", "250"))

lock = threading.RLock()
ACTIVE_JOBS: set[str] = set()  # projetos com render/busca/export em andamento

# Etapas do robô, na ordem em que acontecem.
STAGES: list[tuple[str, str]] = [
    ("input", "Receber arquivos"),
    ("parse", "Ler legendas e dividir em cenas"),
    ("search", "Buscar mídia nos bancos"),
    ("review", "Escolher as cenas"),
    ("download", "Baixar mídia"),
    ("segments", "Montar os clipes com o estilo"),
    ("join", "Unir a timeline"),
    ("audio", "Mixar narração e música"),
    ("finish", "Legendas e exportação do MP4"),
    ("capcut", "Projeto do CapCut"),
]


class Cancelled(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    path = DATA_DIR / project_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return path


def read_state(project_id: str) -> dict[str, Any]:
    path = project_dir(project_id) / "project.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Não foi possível ler os dados do projeto.")


def write_state(project_id: str, state: dict[str, Any]) -> None:
    path = DATA_DIR / project_id / "project.json"
    temp = path.with_suffix(".json.tmp")
    data = json.dumps(state, ensure_ascii=False, indent=1)
    with lock:
        temp.write_text(data, encoding="utf-8")
        # Windows pode bloquear o rename se um leitor tem o arquivo aberto;
        # tentamos algumas vezes antes de cair no fallback de escrita direta.
        for attempt in range(10):
            try:
                temp.replace(path)
                return
            except PermissionError:
                time.sleep(0.05)
        # Fallback: escreve diretamente sem rename atômico
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        path.write_text(data, encoding="utf-8")


def patch_state(project_id: str, fn: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Lê, altera e grava sob lock — evita que o render apague escolhas feitas na tela."""
    with lock:
        state = read_state(project_id)
        fn(state)
        write_state(project_id, state)
        return state


def default_stages() -> dict[str, Any]:
    return {key: {"label": label, "status": "pending", "detail": "", "progress": 0, "started": None, "ended": None} for key, label in STAGES}


class Tracker:
    """Registra o que o robô está fazendo: etapa atual, progresso e um log com horário."""

    def __init__(self, project_id: str):
        self.pid = project_id

    def update(self, stage: str | None = None, status: str | None = None, detail: str | None = None,
               progress: int | None = None, overall: int | None = None, message: str | None = None,
               log: str | None = None, level: str = "info", **fields: Any) -> None:
        def fn(s: dict[str, Any]) -> None:
            stages = s.setdefault("stages", default_stages())
            if stage:
                st = stages.setdefault(stage, {"label": stage, "status": "pending", "detail": "", "progress": 0, "started": None, "ended": None})
                if status:
                    st["status"] = status
                    if status == "running":
                        if not st.get("started") or st.get("ended"):
                            st["started"] = now_iso()
                        st["ended"] = None
                        s["current_stage"] = stage
                    elif status in ("done", "failed", "skipped", "waiting"):
                        st["ended"] = now_iso()
                if detail is not None:
                    st["detail"] = detail
                if progress is not None:
                    st["progress"] = max(0, min(100, int(progress)))
                if status == "done":
                    st["progress"] = 100
            elif status:  # sem etapa: é o status do projeto inteiro (ex.: "complete")
                s["status"] = status
            if overall is not None:
                s["progress"] = max(0, min(100, int(overall)))
            if message is not None:
                s["message"] = message
            for k, v in fields.items():
                s[k] = v
            if log:
                seq = int(s.get("log_seq", 0)) + 1
                s["log_seq"] = seq
                entries = s.setdefault("log", [])
                entries.append({"n": seq, "t": now_iso(), "stage": stage or s.get("current_stage"), "level": level, "msg": log})
                if len(entries) > 500:
                    del entries[: len(entries) - 500]
            s["updated_at"] = now_iso()

        patch_state(self.pid, fn)

    def log(self, msg: str, level: str = "info", stage: str | None = None) -> None:
        self.update(stage=stage, log=msg, level=level)

    def cancelled(self) -> bool:
        try:
            return bool(read_state(self.pid).get("cancel_requested"))
        except HTTPException:
            return True

    def check(self) -> None:
        if self.cancelled():
            raise Cancelled()


# ---------------------------------------------------------------- ferramentas de mídia

def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg não está instalado no servidor. Consulte o README para configurar o ambiente.")
    return path


def ffprobe_path() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("FFprobe não está instalado no servidor. Consulte o README para configurar o ambiente.")
    return path


_filter_cache: dict[str, bool] = {}


def ffmpeg_has_filter(name: str) -> bool:
    if name not in _filter_cache:
        try:
            out = subprocess.run([ffmpeg_path(), "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
            _filter_cache[name] = bool(re.search(rf"\s{re.escape(name)}\s", out))
        except Exception:
            _filter_cache[name] = False
    return _filter_cache[name]


def probe_media(path: Path) -> dict[str, Any]:
    """Duração, dimensões e se tem vídeo/áudio."""
    result = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Não consegui ler o arquivo de mídia ({path.name}).")
    data = json.loads(result.stdout or "{}")
    info: dict[str, Any] = {"duration": 0.0, "width": 0, "height": 0, "has_video": False, "has_audio": False}
    try:
        info["duration"] = float((data.get("format") or {}).get("duration") or 0)
    except ValueError:
        pass
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not info["has_video"]:
            info["has_video"] = True
            info["width"] = int(stream.get("width") or 0)
            info["height"] = int(stream.get("height") or 0)
        elif stream.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def media_duration(path: Path) -> float:
    info = probe_media(path)
    if info["duration"] <= 0:
        raise RuntimeError("O arquivo de áudio não informou uma duração válida. Envie um MP3, WAV ou M4A válido.")
    return max(0.1, info["duration"])


def run_ffmpeg(cmd: list[str], *, total: float | None = None, on_progress: Callable[[float], None] | None = None,
               timeout: float = 3600, cancel_check: Callable[[], bool] | None = None) -> None:
    """Executa o FFmpeg lendo o progresso em tempo real; permite cancelar."""
    full = [cmd[0], "-nostdin", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats", *cmd[1:]]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err_lines: list[str] = []

    def drain() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            err_lines.append(line)
            if len(err_lines) > 200:
                del err_lines[:100]

    threading.Thread(target=drain, daemon=True).start()
    start = time.monotonic()
    last_emit = 0.0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel_check and cancel_check():
                proc.kill()
                raise Cancelled()
            if time.monotonic() - start > timeout:
                proc.kill()
                raise subprocess.TimeoutExpired(full, timeout)
            if on_progress and total and line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                if time.monotonic() - last_emit > 1.2:
                    last_emit = time.monotonic()
                    on_progress(max(0.0, min(1.0, seconds / total)))
        code = proc.wait(timeout=30)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        raise
    if code != 0:
        details = "".join(err_lines)[-1800:] or "Erro desconhecido no FFmpeg"
        raise RuntimeError(f"Falha no FFmpeg: {details}")
