"""Ponte para o servidor local do flow-agent (kodelyx/flow-agent).

A tela "Flow Agent" da aba Chaves de API já existia, mas nada no app chamava a
geração por ela. Este módulo é essa peça: quando o Flow Agent está ativo, a
geração de imagem/vídeo passa a sair do motor local (`flow-go`), usando a conta
do Google Flow logada no Chrome, em vez da Gemini API paga.

O servidor do flow-agent expõe:

    GET  /health
    POST /api/v1/image   {prompt, aspect, count, model}
    POST /api/v1/video   {prompt, aspect, duration, quality, start_image, model}
    POST /api/v1/upload-reference   multipart file -> devolve {"path": ...}
    GET  /api/v1/media/<arquivo>
    GET  /api/v1/balance

Cada geração devolve o objeto do motor, com ``files: [{"path": ...}]``. O
arquivo pode estar no disco (servidor local) ou só do lado do servidor: os dois
casos são cobertos — copiamos do caminho quando ele existe, senão baixamos por
``/api/v1/media/<nome>``.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import requests

import project_config

DEFAULT_URL = "http://localhost:8001"
IMAGE_TIMEOUT = (10, 300)
VIDEO_TIMEOUT = (10, 1800)
REFERENCE_TIMEOUT = (10, 120)

# O modelo `narwhal` (padrão do binário) volta vazio nesta conta; `harbor_seal`
# gera normalmente. Pode ser trocado por FLOW_AGENT_IMAGE_MODEL no ambiente.
DEFAULT_IMAGE_MODEL = "harbor_seal"
DEFAULT_VIDEO_MODEL = "veo"

# O /health é consultado em toda abertura de tela; guardar por alguns segundos
# evita pagar o timeout quando o servidor está desligado.
_HEALTH_TTL = 10.0
_health_cache: dict[str, Any] = {"at": 0.0, "url": "", "value": None}


def config() -> dict[str, Any]:
    """A seção ``flow_agent`` da configuração global do app."""
    try:
        return project_config.load_system_config().get("flow_agent", {}) or {}
    except Exception:
        return {}


def enabled() -> bool:
    """O usuário ligou o Flow Agent na tela de Chaves?"""
    return bool(config().get("ativo"))


def base_url() -> str:
    return str(config().get("url") or DEFAULT_URL).rstrip("/")


def health(timeout: float = 4.0, use_cache: bool = True) -> dict[str, Any] | None:
    """Resposta do ``/health`` do servidor, ou ``None`` se ele não respondeu."""
    url = base_url()
    now = time.monotonic()
    if use_cache and _health_cache["url"] == url and now - _health_cache["at"] < _HEALTH_TTL:
        return _health_cache["value"]

    value: dict[str, Any] | None = None
    try:
        response = requests.get(f"{url}/health", timeout=timeout)
        if response.ok:
            data = response.json()
            if isinstance(data, dict):
                value = data
    except Exception:
        value = None

    _health_cache.update({"at": now, "url": url, "value": value})
    return value


def available() -> bool:
    """Ativo na configuração **e** respondendo agora."""
    return enabled() and health() is not None


def image_model() -> str:
    return (os.getenv("FLOW_AGENT_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL


def video_model() -> str:
    return (os.getenv("FLOW_AGENT_VIDEO_MODEL") or DEFAULT_VIDEO_MODEL).strip() or DEFAULT_VIDEO_MODEL


# --------------------------------------------------------------------------- #
# chamadas
# --------------------------------------------------------------------------- #


def _post(path: str, payload: dict[str, Any], timeout: tuple[int, int]) -> dict[str, Any]:
    url = base_url()
    try:
        response = requests.post(f"{url}{path}", json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"O Flow Agent não respondeu em {url}. Inicie o servidor do flow-agent "
            "e confira a URL na aba Chaves de API."
        ) from exc

    if not response.ok:
        detail = response.text[:300]
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("detail"):
                detail = str(body["detail"])[:300]
        except Exception:
            pass
        raise RuntimeError(f"O Flow Agent respondeu {response.status_code}: {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("O Flow Agent devolveu uma resposta que não é JSON.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("O Flow Agent devolveu um formato inesperado.")
    return data


def _upload_file(path: str, file_path: str, field_name: str = "file", timeout: tuple[int, int] = REFERENCE_TIMEOUT) -> str:
    """Faz upload de um arquivo para o servidor e devolve o caminho salvo."""
    url = base_url()
    try:
        with open(file_path, "rb") as fh:
            files = {field_name: (Path(file_path).name, fh)}
            response = requests.post(f"{url}{path}", files=files, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"O Flow Agent não respondeu em {url}.") from exc
    except OSError as exc:
        raise RuntimeError(f"Não foi possível ler o arquivo {file_path}.") from exc

    if not response.ok:
        detail = response.text[:300]
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("detail"):
                detail = str(body["detail"])[:300]
        except Exception:
            pass
        raise RuntimeError(f"O Flow Agent respondeu {response.status_code}: {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("O Flow Agent devolveu uma resposta que não é JSON.") from exc
    if isinstance(data, dict) and data.get("path"):
        return str(data["path"])
    raise RuntimeError("O Flow Agent não devolveu o caminho do arquivo enviado.")


def _files(result: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in result.get("files") or []:
        raw = item.get("path") if isinstance(item, dict) else item
        if raw:
            out.append(str(raw))
    return out


def _no_output(result: dict[str, Any]) -> str:
    return (
        "O Flow Agent não devolveu arquivo "
        f"(status={result.get('status')!r}, job={result.get('job_id')!r}, "
        f"conta={result.get('account_id')!r}). "
        "Confira os créditos e a sessão na aba Chaves de API."
    )


def _download(filename: str, target: Path) -> None:
    """Baixa um arquivo servido por ``/api/v1/media``."""
    url = f"{base_url()}/api/v1/media/{filename}"
    try:
        with requests.get(url, stream=True, timeout=(10, 300)) as response:
            if not response.ok:
                raise RuntimeError(
                    f"O Flow Agent não serviu o arquivo {filename} ({response.status_code})."
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                for chunk in response.iter_content(1024 * 256):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        raise RuntimeError(f"Falha ao baixar {filename} do Flow Agent: {exc}") from exc


def _materialize(result: dict[str, Any], dest: Path, kind: str) -> Path:
    """Traz o(s) arquivo(s) do resultado para ``dest`` e devolve o primeiro."""
    paths = _files(result)
    if not paths:
        raise RuntimeError(_no_output(result))

    default_suffix = ".mp4" if kind == "video" else ".png"
    first: Path | None = None

    for index, raw in enumerate(paths):
        source = Path(raw)
        suffix = (source.suffix or default_suffix).lower()
        if index == 0:
            target = dest.with_suffix(suffix)
        else:
            target = dest.with_name(f"{dest.name}_{index}").with_suffix(suffix)

        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        else:
            _download(source.name, target)

        if not target.is_file() or target.stat().st_size < 1000:
            raise RuntimeError("O arquivo devolvido pelo Flow Agent está vazio.")

        if first is None:
            first = target

    return first  # type: ignore[return-value]


def _duration(seconds: Any) -> str:
    """Converte o número de segundos do app para ``4s|6s|8s|10s``."""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        value = 6
    value = min((4, 6, 8, 10), key=lambda candidate: abs(candidate - value))
    return f"{value}s"


def _video_aspect(ratio: str) -> str:
    return "9:16" if ratio in ("9:16", "portrait") else "16:9"


# --------------------------------------------------------------------------- #
# interface usada por flow.py
# --------------------------------------------------------------------------- #


def generate_image(prompt: str, ratio: str, dest: Path, count: int = 1, model: str | None = None,
                   reference_image: str | None = None) -> Path:
    """Gera imagem(ns) pelo Flow Agent e grava em ``dest``."""
    aspect = ratio if ratio in ("16:9", "9:16", "1:1", "4:3", "3:4") else "16:9"
    payload: dict[str, Any] = {
        "prompt": prompt,
        "aspect": aspect,
        "count": max(1, min(4, int(count or 1))),
        "model": model or image_model(),
    }
    if reference_image:
        payload["reference_image"] = str(reference_image)
    return _materialize(_post("/api/v1/image", payload, IMAGE_TIMEOUT), dest, "image")


def generate_video(
    prompt: str,
    ratio: str,
    seconds: Any,
    dest: Path,
    quality: str = "720p",
    start_image: str | None = None,
    model: str | None = None,
) -> Path:
    """Gera um clipe pelo Flow Agent e grava em ``dest``."""
    payload: dict[str, Any] = {
        "prompt": prompt,
        "aspect": _video_aspect(ratio),
        "duration": _duration(seconds),
        "quality": quality if quality in ("360p", "720p") else "720p",
        "model": model or video_model(),
    }
    if start_image:
        payload["start_image"] = str(start_image)
    return _materialize(_post("/api/v1/video", payload, VIDEO_TIMEOUT), dest, "video")


def upload_reference(file_path: str) -> str:
    """Envia uma imagem de referência para o servidor e devolve o caminho salvo."""
    return _upload_file("/api/v1/upload-reference", file_path, field_name="file")


def balance() -> dict[str, Any]:
    """Créditos por conta (somente leitura)."""
    try:
        response = requests.get(f"{base_url()}/api/v1/balance", timeout=20)
        if response.ok and isinstance(response.json(), dict):
            return response.json()
    except Exception:
        pass
    return {"accounts": [], "total_credits": 0, "unread": 0}
