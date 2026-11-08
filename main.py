from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import requests
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

import flow
import groq_transcribe
import ia_scenes
import job_queue
import keys_mgr
import media_fetcher
import media_providers
import skills
import skills_video
import narration_engine as nar
import narration_proxy as nar_proxy
import providers
import project_config
import scene_planner
import styles
import youtube_mgr
from capcut import build_capcut_package
import capcut_draft
from capcut_draft import DRAFTS_DIR
from cost_ledger import register_cost, list_costs, total_costs
from providers_base import MediaProvider, ImageGenProvider, VideoGenProvider, AvatarProvider, MediaFetcher
from render import build_mix_cmd, music_path, render_project
from scenes import auto_pick, group_cues, make_query, make_youtube_query, parse_srt, query_variants
from store import (
    ACTIVE_JOBS, BASE_DIR, DATA_DIR, MAX_MEDIA_MB, MUSIC_DIR, PREVIEW_DIR, Cancelled, Tracker, default_stages, ffmpeg_has_filter,
    ffmpeg_path, lock, media_duration, now_iso, patch_state, probe_media, project_dir, read_state, run_ffmpeg, write_state,
)

APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
MAX_SCENES = int(os.getenv("MAX_SCENES", "120"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "800"))
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg")
MEDIA_IMG = (".jpg", ".jpeg", ".png", ".webp")
MEDIA_VID = (".mp4", ".mov", ".webm", ".m4v")

app = FastAPI(title="Faceless Cloud Studio", version="0.4.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ------------------------------------------------------------------ configurações do projeto

DEFAULT_AUDIO = {"music_id": None, "music_volume": 0.14, "narration_volume": 1.0, "ducking": True, "duck_level": "medium",
                 "fade_in": 2.0, "fade_out": 3.0, "loop": True, "normalize": False}


def _num(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_settings(raw: dict[str, Any] | None, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Valida o que veio da tela e completa com os padrões."""
    raw = raw or {}
    cur = base or {}
    out: dict[str, Any] = {}
    out["ratio"] = raw.get("ratio", cur.get("ratio", "16:9"))
    if out["ratio"] not in ("16:9", "9:16", "1:1"):
        out["ratio"] = "16:9"
    out["quality"] = raw.get("quality", cur.get("quality", "720p"))
    if out["quality"] not in ("720p", "1080p"):
        out["quality"] = "720p"
    sources = raw.get("sources", cur.get("sources", ["pexels_video"]))
    out["sources"] = [s for s in sources if s in providers.SOURCE_IDS] if isinstance(sources, list) else ["pexels_video"]
    out["media_pref"] = raw.get("media_pref", cur.get("media_pref", "mixed"))
    if out["media_pref"] not in ("mixed", "video", "image"):
        out["media_pref"] = "mixed"
    out["per_source"] = int(_num(raw.get("per_source", cur.get("per_source", 3)), 1, 8, 3))
    out["pacing"] = raw.get("pacing", cur.get("pacing", "balanced"))
    if out["pacing"] not in styles.PACING:
        out["pacing"] = "balanced"
    out["search_lang"] = raw.get("search_lang", cur.get("search_lang", "auto"))
    if out["search_lang"] not in ("auto", "pt", "en"):
        out["search_lang"] = "auto"
    out["query_extra"] = " ".join(str(raw.get("query_extra", cur.get("query_extra", ""))).split())[:60]
    template = raw.get("template", cur.get("template", styles.DEFAULT_TEMPLATE))
    out["template"] = template if template in styles.TEMPLATE_INDEX else styles.DEFAULT_TEMPLATE
    out["style"] = styles.sanitize_overrides(raw["style"]) if "style" in raw else cur.get("style", {})
    audio = {**DEFAULT_AUDIO, **(cur.get("audio") or {})}
    for key, value in (raw.get("audio") or {}).items():
        if key in DEFAULT_AUDIO:
            audio[key] = value
    audio["music_volume"] = _num(audio["music_volume"], 0.0, 1.0, 0.14)
    audio["narration_volume"] = _num(audio["narration_volume"], 0.0, 2.0, 1.0)
    audio["fade_in"] = _num(audio["fade_in"], 0.0, 15.0, 2.0)
    audio["fade_out"] = _num(audio["fade_out"], 0.0, 15.0, 3.0)
    audio["ducking"] = bool(audio["ducking"])
    audio["loop"] = bool(audio["loop"])
    audio["normalize"] = bool(audio["normalize"])
    if audio["duck_level"] not in ("low", "medium", "high"):
        audio["duck_level"] = "medium"
    mid = audio.get("music_id")
    audio["music_id"] = mid if isinstance(mid, str) and mid.isalnum() else None
    out["audio"] = audio
    out["autopilot"] = bool(raw.get("autopilot", cur.get("autopilot", False)))
    out["auto_capcut"] = bool(raw.get("auto_capcut", cur.get("auto_capcut", False)))
    return out


# ------------------------------------------------------------------ busca de mídia (etapa "search")

def analyze_project(pid: str) -> None:
    """Busca opções de mídia para cada cena. No piloto automático, escolhe e já renderiza."""
    if pid in ACTIVE_JOBS:
        return
    ACTIVE_JOBS.add(pid)
    T = Tracker(pid)
    try:
        state = read_state(pid)
        settings = state["settings"]
        scenes = state["scenes"]
        if not settings["sources"]:
            raise RuntimeError("Selecione pelo menos uma fonte de mídia na aba Mídia.")
        patch_state(pid, lambda s: s.update({"status": "searching", "error": None, "cancel_requested": False, "progress": 0, "message": "Buscando mídia nos bancos selecionados..."}))
        T.update(stage="search", status="running", detail=f"0 de {len(scenes)} cenas", progress=0,
                 log=f"Buscando em {len(settings['sources'])} fontes para {len(scenes)} cenas.")
        orientation = providers.orientation_for(settings["ratio"])
        counts: dict[str, int] = {}
        warnings: list[str] = []
        total_found = 0
        for idx, scene in enumerate(scenes):
            T.check()
            keep = [o for o in scene.get("options", []) if o.get("local_file")]
            options, messages = providers.search_scene_assets(
                scene["query"], settings["sources"], counts,
                per=settings["per_source"], orientation=orientation,
                pref=settings["media_pref"], project_id=pid,
                queries=scene.get("search_queries"), smart=True,
            )
            for m in messages:
                if m not in warnings:
                    warnings.append(m)
                    T.log(m, "warn", stage="search")
            scene_options = keep + options
            total_found += len(options)

            def save(s: dict[str, Any], i=idx, opts=scene_options) -> None:
                sc = s["scenes"][i]
                sc["options"] = opts
                sc["selected"] = 0
                sc["status"] = "found" if opts else "empty"
                s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
            patch_state(pid, save)
            T.update(stage="search", detail=f"{idx + 1} de {len(scenes)} cenas", progress=int(100 * (idx + 1) / len(scenes)),
                     overall=int(100 * (idx + 1) / len(scenes)) if not settings["autopilot"] else int(30 * (idx + 1) / len(scenes)),
                     message=f"Buscando mídia: cena {idx + 1} de {len(scenes)}")
        empty = sum(1 for s in read_state(pid)["scenes"] if not s.get("options"))
        T.update(stage="search", status="done", detail=f"{total_found} opções encontradas" + (f" · {empty} cenas sem resultado" if empty else ""),
                 log=f"Busca concluída: {total_found} opções" + (f"; {empty} cenas ficaram sem resultado" if empty else "") + ".", level="warn" if empty else "info")

        def pick(s: dict[str, Any]) -> None:
            auto_pick(s["scenes"], settings["media_pref"], settings["ratio"])
            s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
        patch_state(pid, pick)
        if settings["autopilot"]:
            T.update(stage="review", status="done", detail="Escolha automática (piloto automático)", log="Piloto automático: escolhi a melhor opção de cada cena, sem repetir mídia.")
            ACTIVE_JOBS.discard(pid)
            render_project(pid)
            return
        T.update(stage="review", status="waiting", detail="Aguardando você escolher as cenas e iniciar a montagem",
                 overall=100, message="Cenas prontas. Revise e inicie a montagem.", log="Pré-seleção feita. Revise as cenas e clique em Montar vídeo.")
        patch_state(pid, lambda s: s.update({"status": "ready"}))
    except Cancelled:
        patch_state(pid, lambda s: s.update({"status": "ready", "message": "Busca cancelada.", "cancel_requested": False}))
        T.log("Busca cancelada por você.", "warn")
    except Exception as exc:
        patch_state(pid, lambda s: s.update({"status": "failed", "error": str(exc), "message": str(exc)}))
        T.update(stage="search", status="failed", detail=str(exc)[:200], log=str(exc)[:500], level="error")
    finally:
        ACTIVE_JOBS.discard(pid)


def analyze_empty_scenes(pid: str, empty_ids: set[str]) -> None:
    """Busca mídia somente para cenas com options vazias, preservando as que já têm resultado."""
    if pid in ACTIVE_JOBS:
        return
    ACTIVE_JOBS.add(pid)
    T = Tracker(pid)
    try:
        state = read_state(pid)
        settings = state["settings"]
        scenes = [s for s in state["scenes"] if s["id"] in empty_ids]
        if not settings["sources"]:
            raise RuntimeError("Selecione pelo menos uma fonte de mídia na aba Mídia.")
        total = len(scenes)
        T.update(stage="search", status="running", detail=f"0 de {total} cenas sem mídia", progress=0,
                 log=f"Buscando apenas as {total} cenas que ficaram sem mídia.")
        orientation = providers.orientation_for(settings["ratio"])
        counts: dict[str, int] = {}
        total_found = 0
        for idx, scene in enumerate(scenes):
            T.check()
            options, messages = providers.search_scene_assets(
                scene["query"], settings["sources"], counts,
                per=settings["per_source"], orientation=orientation,
                pref=settings["media_pref"], project_id=pid,
                queries=scene.get("search_queries"), smart=True,
            )
            for m in messages:
                T.log(m, "warn", stage="search")
            total_found += len(options)

            def save(s: dict[str, Any], sid=scene["id"], opts=options) -> None:
                for sc in s["scenes"]:
                    if sc["id"] == sid:
                        sc["options"] = opts
                        sc["selected"] = 0
                        sc["status"] = "found" if opts else "empty"
                        break
                s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
            patch_state(pid, save)
            T.update(stage="search", detail=f"{idx + 1} de {total} cenas", progress=int(100 * (idx + 1) / total),
                     overall=int(100 * (idx + 1) / total),
                     message=f"Buscando cenas sem mídia: {idx + 1} de {total}")
        still_empty = sum(1 for s in read_state(pid)["scenes"] if not s.get("options"))
        T.update(stage="search", status="done",
                 detail=f"{total_found} opções encontradas" + (f" · {still_empty} cenas ainda sem resultado" if still_empty else ""),
                 log=f"Busca de cenas vazias: {total_found} opções" + (f"; {still_empty} ainda sem resultado" if still_empty else " – todas preenchidas!") + ".",
                 level="warn" if still_empty else "info")
        def pick(s: dict[str, Any]) -> None:
            auto_pick(s["scenes"], settings["media_pref"], settings["ratio"])
            s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
        patch_state(pid, pick)
        patch_state(pid, lambda s: s.update({"status": "ready"}))
    except Cancelled:
        patch_state(pid, lambda s: s.update({"status": "ready", "message": "Busca cancelada.", "cancel_requested": False}))
        T.log("Busca cancelada por você.", "warn")
    except Exception as exc:
        patch_state(pid, lambda s: s.update({"status": "failed", "error": str(exc), "message": str(exc)}))
        T.update(stage="search", status="failed", detail=str(exc)[:200], log=str(exc)[:500], level="error")
    finally:
        ACTIVE_JOBS.discard(pid)


def run_render_job(pid: str) -> None:
    if pid in ACTIVE_JOBS:
        return
    ACTIVE_JOBS.add(pid)
    try:
        render_project(pid)
    finally:
        ACTIVE_JOBS.discard(pid)


def run_capcut_job(pid: str) -> None:
    if pid in ACTIVE_JOBS:
        return
    ACTIVE_JOBS.add(pid)
    T = Tracker(pid)
    try:
        build_capcut_package(pid, T)
    except Cancelled:
        patch_state(pid, lambda s: s.update({"capcut": {"status": "none"}, "cancel_requested": False}))
        T.update(stage="capcut", status="pending", log="Exportação para o CapCut cancelada.", level="warn")
    except Exception as exc:
        patch_state(pid, lambda s: s.update({"capcut": {"status": "failed", "error": str(exc)[:300]}}))
        T.update(stage="capcut", status="failed", detail=str(exc)[:200], log=f"Falha ao montar o projeto do CapCut: {exc}", level="error")
    finally:
        ACTIVE_JOBS.discard(pid)


# ------------------------------------------------------------------ modelos

class SceneUpdate(BaseModel):
    selected: int | None = None
    query: str | None = None


class SceneSearchBody(BaseModel):
    query: str | None = None
    sources: list[str] | None = None


class GenerateBody(BaseModel):
    kind: str = "image"          # image | video
    prompt: str
    seconds: int = 6


class LoginBody(BaseModel):
    password: str


class FishPreviewBody(BaseModel):
    text: str
    reference_id: str | None = None
    model: str = "s2.1-pro-free"


class NarrationCreateBody(BaseModel):
    text: str
    reference_id: str | None = None
    model: str = "s2.1-pro-free"
    speed: float = 1.0
    stability: float = 0.5
    expressiveness: float = 0.5
    max_concurrent: int = 4


class KeysUpdateBody(BaseModel):
    keys: dict[str, str]


class KeyTestBody(BaseModel):
    key_id: str
    key_value: str | None = None


class YouTubeSearchBody(BaseModel):
    query: str
    per: int = 6
    orientation: str = "landscape"


class YouTubeDownloadBody(BaseModel):
    url: str
    project_id: str | None = None
    scene_id: str | None = None


class FlowGenerateBody(BaseModel):
    prompt: str
    kind: str = "image"
    ratio: str = "16:9"
    seconds: int = 6
    model: str | None = None
    reference_image: str | None = None


class FlowBatchBody(BaseModel):
    prompts: list[str]
    kind: str = "image"
    ratio: str = "16:9"
    seconds: int = 6
    model: str | None = None


# ------------------------------------------------------------------ Fila de geração do Flow

FLOW_QUEUE_DIR = DATA_DIR / "flow_queue"
FLOW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def _queue_path(item_id: str) -> Path:
    return FLOW_QUEUE_DIR / f"{item_id}.json"


def _queue_list() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not FLOW_QUEUE_DIR.exists():
        return items
    for p in sorted(FLOW_QUEUE_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


def _queue_save(item: dict[str, Any]) -> None:
    _queue_path(item["id"]).write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")


def _queue_remove(item_id: str) -> None:
    p = _queue_path(item_id)
    if p.exists():
        p.unlink()


@app.get("/api/flow/queue")
def flow_queue():
    return {"items": _queue_list()}


@app.post("/api/flow/queue/retry")
def flow_queue_retry(body: dict[str, Any]):
    """Reprocessa um item da fila que deu erro."""
    item_id = body.get("id")
    if not item_id:
        raise HTTPException(status_code=400, detail="Informe o id do item.")
    p = _queue_path(item_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Item não encontrado na fila.")
    item = json.loads(p.read_text(encoding="utf-8"))
    if item.get("status") != "erro":
        raise HTTPException(status_code=400, detail="Somente itens com erro podem ser refeitos.")
    item["status"] = "processando"
    item["erro"] = None
    _queue_save(item)
    background_tasks = BackgroundTasks()
    background_tasks.add_task(_run_queue_item, item)
    return {"ok": True, "id": item_id}


def _run_queue_item(item: dict[str, Any]) -> None:
    """Executa um item da fila em background e atualiza o status."""
    item_id = item["id"]
    try:
        prompt = item.get("prompt", "").strip()
        kind = item.get("kind", "image")
        ratio = item.get("ratio", "16:9")
        seconds = item.get("seconds", 6)
        model = item.get("model")
        reference_image = item.get("reference_image")
        if len(prompt) < 5:
            raise RuntimeError("Prompt muito curto.")
        name = f"flow_{uuid.uuid4().hex[:8]}"
        dest = flow.FLOW_GALLERY_DIR / name
        if kind == "video":
            out_file = flow.generate_video(prompt, ratio, seconds, dest, model=model)
        else:
            out_file = flow.generate_image(prompt, ratio, dest, model=model, reference_image=reference_image)
        meta_file = out_file.with_suffix(out_file.suffix + ".json")
        meta_file.write_text(json.dumps({"prompt": prompt, "kind": kind, "ratio": ratio, "model": model, "created_at": now_iso()}, ensure_ascii=False), encoding="utf-8")
        item["status"] = "concluido"
        item["filename"] = out_file.name
        item["url"] = f"/api/flow/gallery/{out_file.name}"
        item["size_mb"] = round(out_file.stat().st_size / (1024 * 1024), 2)
        item["erro"] = None
    except Exception as exc:
        item["status"] = "erro"
        item["erro"] = str(exc)[:300]
    finally:
        _queue_save(item)


# ------------------------------------------------------------------ Limpeza de fila e galeria

class QueueClearBody(BaseModel):
    status: str | None = None  # "concluido" | "erro" | None = ambos


@app.post("/api/flow/queue/clear")
def flow_queue_clear(body: QueueClearBody | None = None):
    """Remove itens da fila (concluídos, com erro ou ambos)."""
    target = (body.status or "").strip().lower() if body else ""
    removed = 0
    for p in list(FLOW_QUEUE_DIR.glob("*.json")):
        try:
            item = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            p.unlink(missing_ok=True)
            removed += 1
            continue
        if not target or item.get("status") == target:
            # Se concluiu e tem arquivo, deixa o arquivo na galeria (só remove da fila)
            p.unlink(missing_ok=True)
            removed += 1
    return {"ok": True, "removed": removed, "status": target or "todos"}


@app.post("/api/flow/gallery/clear")
def flow_gallery_clear():
    """Remove todos os arquivos da galeria de mídia gerada."""
    removed = 0
    for p in list(flow.FLOW_GALLERY_DIR.glob("*")):
        if p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
    return {"ok": True, "removed": removed}


# ------------------------------------------------------------------ Conectar item da fila a um projeto (cena)

class QueueToProjectBody(BaseModel):
    project_id: str
    scene_id: str


@app.post("/api/flow/queue/item/{item_id}/to-project")
def flow_queue_item_to_project(item_id: str, body: QueueToProjectBody):
    """Adiciona um item concluído da fila como opção de mídia em uma cena do projeto."""
    p = _queue_path(item_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Item não encontrado na fila.")
    item = json.loads(p.read_text(encoding="utf-8"))
    if item.get("status") != "concluido" or not item.get("filename"):
        raise HTTPException(status_code=400, detail="Somente itens concluídos podem ser adicionados ao projeto.")

    state = read_state(body.project_id)
    scene = _find_scene(state, body.scene_id)

    # Copia o arquivo da galeria para os uploads do projeto
    src = flow.FLOW_GALLERY_DIR / item["filename"]
    if not src.exists():
        raise HTTPException(status_code=404, detail="Arquivo da galeria não encontrado.")

    folder = project_dir(body.project_id)
    uploads = folder / "uploads"
    uploads.mkdir(exist_ok=True)
    dest_name = f"flow_{item['filename']}"
    dest = uploads / dest_name
    shutil.copyfile(src, dest)

    is_video = dest.suffix.lower() in (".mp4", ".mov")
    thumb_rel = f"uploads/{dest_name}"
    if is_video:
        thumb = uploads / f"{dest_name}.jpg"
        subprocess.run([ffmpeg_path(), "-y", "-ss", "0.3", "-i", str(dest), "-vf", "scale=480:-2", "-frames:v", "1", str(thumb)], capture_output=True, timeout=60)
        thumb_rel = f"uploads/{dest_name}.jpg" if thumb.exists() else thumb_rel

    info = probe_media(dest)
    option = {
        "id": dest_name, "provider": "Flow Agent", "media_type": "video" if is_video else "image",
        "download_url": "", "local_file": f"uploads/{dest_name}",
        "thumbnail": f"/api/projects/{body.project_id}/files/{thumb_rel.split('/', 1)[1]}",
        "source_url": "", "photographer": "Flow Agent",
        "license": "Gerado via Flow Agent", "width": info["width"], "height": info["height"],
        "duration": info["duration"] if is_video else None, "prompt": item.get("prompt", ""),
    }

    def fn(s: dict[str, Any]) -> None:
        sc = _find_scene(s, body.scene_id)
        sc.setdefault("options", []).insert(0, option)
        sc["selected"] = 0
        sc["status"] = "found"
        s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
    return {"scene": _find_scene(patch_state(body.project_id, fn), body.scene_id), "option": option}


@app.post("/api/flow/upload-txt-prompts")
async def flow_upload_txt_prompts(file: UploadFile = File(...)):
    """Recebe um arquivo TXT com prompts (um por linha) e devolve a lista."""
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="O arquivo deve ser um TXT válido (UTF-8).")
    prompts = [p.strip() for p in text.splitlines() if p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="O arquivo não contém prompts válidos.")
    if len(prompts) > 500:
        raise HTTPException(status_code=400, detail="Máximo de 500 prompts por arquivo.")
    return {"prompts": prompts, "total": len(prompts)}


def active_app_password() -> str:
    pwd = os.getenv("APP_PASSWORD", "").strip()
    return pwd if keys_mgr.is_active_key(pwd) else ""


class PasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        pwd = active_app_password()
        if not pwd:
            return await call_next(request)
        path = request.url.path
        if path in ("/", "/api/login", "/api/health", "/favicon.ico") or path.startswith("/static/"):
            return await call_next(request)
        token = request.cookies.get("faceless_session", "")
        expected = hashlib.sha256(pwd.encode()).hexdigest()
        if not hmac.compare_digest(token, expected):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Acesso protegido. Faça login."}, status_code=401)
            return HTMLResponse("Acesso protegido. Abra o app e faça login.", status_code=401)
        return await call_next(request)


app.add_middleware(PasswordMiddleware)


# ------------------------------------------------------------------ páginas e saúde

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/health")
def health():
    flow_ready = flow.is_ready()
    return {
        "ok": True, "app": "Faceless Cloud Studio", "version": app.version, "password_enabled": bool(active_app_password()),
        "fish_audio": keys_mgr.is_active_key(os.getenv("FISH_API_KEY", "")), "flow_ai": flow_ready,
        "flow_error": None if flow_ready else flow.readiness_error(),
        "groq": groq_transcribe.has_key(),
        "ffmpeg_available": bool(shutil.which("ffmpeg")), "subtitles_available": shutil.which("ffmpeg") is not None and ffmpeg_has_filter("ass"),
        "providers": {s["id"]: s["ready"] for s in providers.public_sources()},
    }


# ------------------------------------------------------------------ chaves de API
@app.get("/api/keys")
def get_keys():
    return {"keys": keys_mgr.get_all_keys_status()}


@app.post("/api/keys")
def save_keys(body: KeysUpdateBody):
    keys_mgr.save_env_keys(body.keys)
    return {"ok": True, "keys": keys_mgr.get_all_keys_status()}


@app.post("/api/keys/test")
def test_key(body: KeyTestBody):
    return keys_mgr.test_provider_key(body.key_id, body.key_value)


# ------------------------------------------------------------------ YouTube
@app.post("/api/youtube/search")
def youtube_search_route(body: YouTubeSearchBody):
    results = youtube_mgr.youtube_search(body.query, per=body.per, orientation=body.orientation)
    return {"results": results}


@app.post("/api/youtube/download")
async def youtube_download_route(body: YouTubeDownloadBody):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Informe a URL ou link do vídeo do YouTube.")

    if body.project_id and body.scene_id:
        state = read_state(body.project_id)
        folder = project_dir(body.project_id)
        _find_scene(state, body.scene_id)
        uploads = folder / "uploads"
        uploads.mkdir(exist_ok=True)
        name = f"yt_{uuid.uuid4().hex[:8]}.mp4"
        dest = uploads / name
        try:
            youtube_mgr.download_youtube_video(url, dest)
            info = probe_media(dest)
            thumb = uploads / f"{name}.jpg"
            subprocess.run([ffmpeg_path(), "-y", "-ss", "0.3", "-i", str(dest), "-vf", "scale=480:-2", "-frames:v", "1", str(thumb)], capture_output=True, timeout=60)
            thumb_rel = thumb.name if thumb.exists() else name
            option = {
                "id": name, "provider": "YouTube", "media_type": "video", "download_url": url, "local_file": f"uploads/{name}",
                "thumbnail": f"/api/projects/{body.project_id}/files/{thumb_rel}", "source_url": url, "photographer": "YouTube",
                "license": "YouTube Video", "width": info["width"], "height": info["height"], "duration": info["duration"],
            }
            def fn(s: dict[str, Any]) -> None:
                sc = _find_scene(s, body.scene_id)
                sc.setdefault("options", []).insert(0, option)
                sc["selected"] = 0
                sc["status"] = "found"
                s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
            return {"scene": _find_scene(patch_state(body.project_id, fn), body.scene_id), "option": option}
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Falha ao baixar vídeo do YouTube: {exc}")
    else:
        gallery_dir = DATA_DIR / "youtube_downloads"
        gallery_dir.mkdir(parents=True, exist_ok=True)
        name = f"yt_{uuid.uuid4().hex[:8]}.mp4"
        dest = gallery_dir / name
        try:
            youtube_mgr.download_youtube_video(url, dest)
            return {"ok": True, "file": name, "url": f"/api/youtube/file/{name}"}
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/youtube/file/{name}")
def get_youtube_downloaded_file(name: str):
    p = (DATA_DIR / "youtube_downloads" / name).resolve()
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(p, media_type="video/mp4")


# ------------------------------------------------------------------ Flow AI & Galeria
@app.get("/api/flow/gallery")
def get_flow_gallery():
    return {"items": flow.list_gallery_items(), "mcp_config": flow.get_mcp_config()}


@app.get("/api/flow/gallery/{name}")
def get_flow_gallery_file(name: str):
    for folder in (flow.FLOW_GALLERY_DIR, flow.MCP_OUT_DIR):
        p = (folder / name).resolve()
        if p.is_file():
            is_video = p.suffix.lower() in (".mp4", ".mov")
            return FileResponse(p, media_type="video/mp4" if is_video else "image/png")
    raise HTTPException(status_code=404, detail="Arquivo da galeria não encontrado.")


@app.post("/api/flow/generate")
def flow_generate_route(body: FlowGenerateBody, background_tasks: BackgroundTasks):
    if not flow.is_ready():
        raise HTTPException(status_code=400, detail=flow.readiness_error())
    prompt = body.prompt.strip()
    if len(prompt) < 5:
        raise HTTPException(status_code=400, detail="Digite uma descrição para a mídia.")
    kind = "video" if body.kind == "video" else "image"
    ratio = body.ratio if body.ratio in ("16:9", "9:16", "1:1") else "16:9"
    item = {
        "id": f"q_{uuid.uuid4().hex[:8]}",
        "prompt": prompt,
        "kind": kind,
        "ratio": ratio,
        "seconds": body.seconds,
        "model": body.model,
        "reference_image": body.reference_image,
        "status": "processando",
        "erro": None,
        "filename": None,
        "url": None,
        "size_mb": None,
        "created_at": now_iso(),
    }
    _queue_save(item)
    background_tasks.add_task(_run_queue_item, item)
    return {"ok": True, "id": item["id"], "status": "processando"}


# ------------------------------------------------------------------ Flow geração em lote (prompts infinitos)

class FlowBatchGenerateBody(BaseModel):
    prompts: list[str]
    kind: str = "image"
    ratio: str = "16:9"
    seconds: int = 6


@app.post("/api/flow/batch-generate")
def flow_batch_generate_route(body: FlowBatchGenerateBody, background_tasks: BackgroundTasks):
    """Gera múltiplas imagens/vídeos em sequência. Usa a Gemini API oficial (Nano Banana/Veo),
    não automação de navegador. O Google Flow não tem API oficial pública."""
    if not flow.is_ready():
        raise HTTPException(status_code=400, detail=flow.readiness_error())
    prompts = [p.strip() for p in (body.prompts or []) if p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="Informe pelo menos um prompt.")
    if len(prompts) > 100:
        raise HTTPException(status_code=400, detail="Máximo de 100 prompts por lote.")
    kind = "video" if body.kind == "video" else "image"
    ratio = body.ratio if body.ratio in ("16:9", "9:16", "1:1") else "16:9"
    ids = []
    for i, prompt in enumerate(prompts):
        item = {
            "id": f"q_{uuid.uuid4().hex[:8]}",
            "prompt": prompt,
            "kind": kind,
            "ratio": ratio,
            "seconds": body.seconds,
            "model": body.model,
            "reference_image": None,
            "status": "processando",
            "erro": None,
            "filename": None,
            "url": None,
            "size_mb": None,
            "created_at": now_iso(),
            "batch_index": i,
        }
        _queue_save(item)
        ids.append(item["id"])
        background_tasks.add_task(_run_queue_item, item)
    return {"ok": True, "total": len(prompts), "ids": ids, "status": "processando"}


# ------------------------------------------------------------------ Flow Blocos (animação 2D por cena)

class FlowBlocksBody(BaseModel):
    script: str
    max_blocks: int = 20
    ratio: str = "16:9"
    project_id: str | None = None
    use_srt: bool = False


class FlowBlockImageBody(BaseModel):
    block_id: str
    prompt: str
    ratio: str = "16:9"
    project_id: str | None = None
    reference_image: str | None = None


FLOW_BLOCKS_DIR = DATA_DIR / "flow_blocks"
FLOW_BLOCKS_DIR.mkdir(parents=True, exist_ok=True)

FLOW_REF_DIR = DATA_DIR / "flow_references"
FLOW_REF_DIR.mkdir(parents=True, exist_ok=True)


def _blocks_dir(project_id: str | None) -> Path:
    d = FLOW_BLOCKS_DIR / (project_id or "sem_projeto")
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.post("/api/flow/blocks-from-script")
def flow_blocks_from_script(body: FlowBlocksBody):
    """Divide um roteiro em blocos e sugere um prompt de imagem para cada um.
    
    Se use_srt for true e houver project_id, lê o SRT do projeto para gerar blocos
    com timestamps de timeline. Caso contrário, divide o texto do roteiro direto.
    """
    if not body.script or not body.script.strip():
        # Tenta pegar o SRT do projeto se use_srt estiver ativo
        if body.use_srt and body.project_id:
            try:
                state = read_state(body.project_id)
                srt_name = state.get("srt_file")
                if srt_name:
                    srt_path = project_dir(body.project_id) / srt_name
                    if srt_path.exists():
                        srt_text = srt_path.read_text(encoding="utf-8-sig", errors="replace")
                        blocos = flow.blocks_from_srt(srt_text, max_blocks=body.max_blocks)
                        d = _blocks_dir(body.project_id)
                        estado = {
                            "ratio": body.ratio,
                            "script": body.script,
                            "source": "srt",
                            "srt_file": srt_name,
                            "blocos": [{"id": b["id"], "texto": b["texto"], "prompt": b["prompt"],
                                        "start": b.get("start", 0), "end": b.get("end", 0),
                                        "imagem": None, "status": "pendente"} for b in blocos],
                            "criado_em": now_iso(),
                        }
                        (d / "blocos.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
                        return {"blocos": blocos, "total": len(blocos), "source": "srt"}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Não consegui ler o SRT do projeto: {exc}")
        raise HTTPException(status_code=400, detail="Cole o roteiro antes de gerar os blocos.")
    try:
        blocos = flow.generate_prompts_from_script(body.script, max_blocks=body.max_blocks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não consegui dividir o roteiro: {exc}")
    if body.project_id:
        d = _blocks_dir(body.project_id)
        estado = {
            "ratio": body.ratio,
            "script": body.script,
            "source": "texto",
            "blocos": [{"id": b["id"], "texto": b["texto"], "prompt": b["prompt"], "imagem": None, "status": "pendente"} for b in blocos],
            "criado_em": now_iso(),
        }
        (d / "blocos.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"blocos": blocos, "total": len(blocos), "source": "texto"}


@app.post("/api/flow/generate-block-image")
def flow_generate_block_image(body: FlowBlockImageBody):
    """Gera a imagem de um bloco específico via Nano Banana (Flow AI)."""
    if not flow.is_ready():
        raise HTTPException(status_code=400, detail=flow.readiness_error())
    prompt = body.prompt.strip()
    if len(prompt) < 5:
        raise HTTPException(status_code=400, detail="O prompt do bloco está vazio.")
    ratio = body.ratio if body.ratio in ("16:9", "9:16", "1:1") else "16:9"
    name = f"block_{uuid.uuid4().hex[:8]}"
    dest = flow.FLOW_GALLERY_DIR / name
    try:
        if body.reference_image:
            out_file = flow.generate_image_with_ref(prompt, ratio, dest, body.reference_image)
        else:
            out_file = flow.generate_image(prompt, ratio, dest)
        meta_file = out_file.with_suffix(out_file.suffix + ".json")
        meta_file.write_text(json.dumps({"prompt": prompt, "kind": "image", "ratio": ratio, "block_id": body.block_id, "project_id": body.project_id, "created_at": now_iso()}, ensure_ascii=False), encoding="utf-8")
        item = {
            "filename": out_file.name,
            "url": f"/api/flow/gallery/{out_file.name}",
            "kind": "image",
            "size_mb": round(out_file.stat().st_size / (1024 * 1024), 2),
            "created_at": now_iso(),
            "prompt": prompt,
        }
        # Atualiza o estado salvo do bloco, se houver projeto
        if body.project_id:
            d = _blocks_dir(body.project_id)
            estado_path = d / "blocos.json"
            if estado_path.exists():
                try:
                    estado = json.loads(estado_path.read_text(encoding="utf-8"))
                    for b in estado.get("blocos", []):
                        if b.get("id") == body.block_id:
                            b["imagem"] = item
                            b["status"] = "concluido"
                            break
                    estado_path.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        return {"ok": True, "item": item}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/flow/upload-reference")
async def flow_upload_reference(reference: UploadFile = File(...)):
    """Recebe uma imagem de referência para usar na geração de blocos (Nano Banana)."""
    suffix = Path(reference.filename or "ref.png").suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(status_code=400, detail="Envie uma imagem PNG, JPG ou WebP como referência.")
    name = f"ref_{uuid.uuid4().hex[:8]}{suffix}"
    dest = FLOW_REF_DIR / name
    size = 0
    try:
        with dest.open("wb") as handle:
            while chunk := await reference.read(1024 * 1024):
                size += len(chunk)
                handle.write(chunk)
    finally:
        await reference.close()
    return {"ok": True, "filename": name, "path": str(dest), "url": f"/api/flow/reference/{name}", "size_mb": round(size / (1024 * 1024), 2)}


@app.get("/api/flow/reference/{name}")
def flow_get_reference(name: str):
    for folder in (FLOW_REF_DIR,):
        p = (folder / name).resolve()
        if p.is_file():
            return FileResponse(p)
    raise HTTPException(status_code=404, detail="Imagem de referência não encontrada.")


@app.get("/api/flow/blocks/{project_id}")
def flow_get_blocks(project_id: str):
    """Devolve os blocos salvos de um projeto (com imagens geradas)."""
    d = _blocks_dir(project_id)
    estado_path = d / "blocos.json"
    if not estado_path.exists():
        return {"blocos": [], "total": 0, "ratio": "16:9"}
    try:
        estado = json.loads(estado_path.read_text(encoding="utf-8"))
        return estado
    except Exception:
        return {"blocos": [], "total": 0, "ratio": "16:9"}


@app.get("/api/flow/mcp-config")
def get_flow_mcp_config():
    return flow.get_mcp_config()


# ------------------------------------------------------------------ Jobs (fila assíncrona)

class JobCreateBody(BaseModel):
    etapa: str
    project_id: str | None = None
    payload: dict[str, Any] | None = None


@app.post("/api/jobs")
def create_job_route(body: JobCreateBody):
    job_id = job_queue.create_job(body.etapa, project_id=body.project_id, payload=body.payload)
    return {"id": job_id, "status": "queued"}


@app.get("/api/jobs")
def list_jobs_route(project_id: str | None = None, etapa: str | None = None,
                    status: str | None = None, limit: int = 50):
    return {"jobs": job_queue.list_jobs(project_id=project_id, etapa=etapa, status=status, limit=limit)}


@app.get("/api/jobs/{job_id}")
def get_job_route(job_id: str):
    job = job_queue.read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return job


# ------------------------------------------------------------------ Custos (ledger)

class CostRegisterBody(BaseModel):
    project_id: str | None = None
    etapa: str
    provedor: str
    modelo: str
    unidades: float
    custo_estimado: float
    moeda: str = "USD"
    metadata: dict[str, Any] | None = None


@app.post("/api/costs")
def register_cost_route(body: CostRegisterBody):
    record_id = register_cost(
        project_id=body.project_id, etapa=body.etapa, provedor=body.provedor,
        modelo=body.modelo, unidades=body.unidades, custo_estimado=body.custo_estimado,
        moeda=body.moeda, metadata=body.metadata,
    )
    return {"id": record_id}


@app.get("/api/costs")
def list_costs_route(project_id: str | None = None, etapa: str | None = None,
                     provedor: str | None = None, limit: int = 200):
    return {"costs": list_costs(project_id=project_id, etapa=etapa,
                                provedor=provedor, limit=limit)}


@app.get("/api/costs/total")
def total_costs_route(project_id: str | None = None):
    return total_costs(project_id=project_id)


# ------------------------------------------------------------------ Configuração do projeto (JSON)

class ConfigSaveBody(BaseModel):
    config: dict[str, Any]


@app.get("/api/config/{project_id}")
def get_config_route(project_id: str):
    return project_config.load_config(project_id)


@app.post("/api/config/{project_id}")
def save_config_route(project_id: str, body: ConfigSaveBody):
    return project_config.save_config(project_id, body.config)


@app.patch("/api/config/{project_id}")
def patch_config_route(project_id: str, patches: dict[str, Any]):
    return project_config.update_config(project_id, patches)


# ------------------------------------------------------------------ Montagem e Acabamento

class MontagemConfigBody(BaseModel):
    modo: str = "parar_se_faltar"          # parar_se_faltar | direto
    cortar_silencios: bool = True
    movimento_imagens: bool = True
    transicao: str = "fade"                # fade | cut | xfade | ...
    fade_inicio_fim: bool = True
    silencia_limiar: str = "-50dB"
    silencia_pausa_maxima: float = 0.25
    transicao_duracao: float = 0.5


@app.get("/api/montagem/{project_id}")
def get_montagem_route(project_id: str):
    """Devolve a configuração de montagem do projeto."""
    cfg = project_config.load_config(project_id)
    return {"montagem": cfg.get("montagem", project_config.DEFAULT_CONFIG["montagem"])}


@app.post("/api/montagem/{project_id}")
def save_montagem_route(project_id: str, body: MontagemConfigBody):
    """Salva a configuração de montagem do projeto."""
    return project_config.update_config(project_id, {"montagem": body.model_dump()})


@app.post("/api/projects/{project_id}/montagem/preview")
def montagem_preview(project_id: str):
    """Simula o que seria renderizado: lista cenas, silêncios detectados, tempo estimado."""
    state = read_state(project_id)
    montagem = state.get("config", {}).get("montagem", {}) if isinstance(state.get("config"), dict) else {}
    montagem = montagem or project_config.load_config(project_id).get("montagem", {})

    scenes = state.get("scenes", [])
    audio_file = state.get("audio_file")
    audio_len = 0.0
    if audio_file:
        try:
            audio_len = media_duration(project_dir(project_id) / audio_file)
        except Exception:
            audio_len = 0.0

    cortar = montagem.get("cortar_silencios", True)
    modo = montagem.get("modo", "parar_se_faltar")

    cenas_sem_media = [s for s in scenes if not s.get("options")]
    pode_render = len(cenas_sem_media) == 0 or modo == "direto"

    return {
        "project_id": project_id,
        "modo": modo,
        "cortar_silencios": cortar,
        "audio_duracao": round(audio_len, 2),
        "cenas_total": len(scenes),
        "cenas_sem_media": len(cenas_sem_media),
        "pode_render": pode_render,
        "transicao": montagem.get("transicao", "fade"),
        "fade_inicio_fim": montagem.get("fade_inicio_fim", True),
        "mensagem": "Pronto para renderizar" if pode_render else f"{len(cenas_sem_media)} cenas sem mídia. Use 'parar_se_faltar' para revisar ou 'direto' para renderizar com fallback.",
    }


# ------------------------------------------------------------------ Provedores (status)

@app.get("/api/providers")
def list_providers_route():
    """Devolve o status de cada provedor configurado."""
    return {
        "media": [p.public_meta() for p in media_providers.PROVIDERS],
        "image_gen": [p.public_meta() for p in ia_scenes.IMAGE_GEN_PROVIDERS],
        "video_gen": [p.public_meta() for p in ia_scenes.VIDEO_GEN_PROVIDERS],
        "avatar": [p.public_meta() for p in []],
        "media_fetcher": [p.public_meta() for p in media_fetcher.FETCHERS],
        "flow_agent": {
            "id": "flow_agent",
            "name": "Google Flow Agent (extensão Chrome)",
            "needs_key": False,
            "ready": bool(project_config.load_system_config().get("flow_agent", {}).get("ativo", False)),
            "url": project_config.load_system_config().get("flow_agent", {}).get("url", ""),
        },
    }


# ------------------------------------------------------------------ Flow Agent (extensão Chrome)

class FlowAgentConfigBody(BaseModel):
    ativo: bool = False
    url: str = "http://localhost:8001"


class FlowAgentImageBody(BaseModel):
    prompt: str
    aspect: str = "16:9"  # 1:1 | 16:9 | 9:16 | 4:3 | 3:4
    count: int = 1


class FlowAgentVideoBody(BaseModel):
    prompt: str
    aspect: str = "landscape"  # landscape | portrait | 16:9 | 9:16
    duration: str = "8s"  # 4s | 6s | 8s | 10s
    quality: str = "720p"  # 360p | 720p
    start_image: str | None = None


def _flow_agent_config() -> dict[str, Any]:
    """Lê a configuração do flow_agent do armazenamento do sistema."""
    try:
        return project_config.load_system_config().get("flow_agent", {
            "ativo": False, "url": "http://localhost:8001", "contas_conectadas": 0, "ultimo_status": "desconhecido"
        })
    except Exception:
        return {"ativo": False, "url": "http://localhost:8001", "contas_conectadas": 0, "ultimo_status": "desconhecido"}


@app.get("/api/flow-agent/config")
def get_flow_agent_config_route():
    """Devolve a configuração do Flow Agent."""
    return _flow_agent_config()


@app.post("/api/flow-agent/config")
def save_flow_agent_config_route(body: FlowAgentConfigBody):
    """Salva a configuração do Flow Agent (URL do servidor local)."""
    return project_config.update_system_config({"flow_agent": body.model_dump()})


@app.get("/api/flow-agent/status")
def flow_agent_status_route():
    """Verifica se o servidor Flow Agent está online e quantas contas estão conectadas."""
    cfg = _flow_agent_config()
    url = cfg.get("url", "http://localhost:8001").rstrip("/")
    try:
        r = requests.get(f"{url}/health", timeout=5)
        if r.ok:
            data = r.json()
            return {
                "online": True,
                "url": url,
                "contas_conectadas": cfg.get("contas_conectadas", 0),
                "ultimo_status": "online",
                "detalhe": data,
            }
        return {
            "online": False,
            "url": url,
            "contas_conectadas": cfg.get("contas_conectadas", 0),
            "ultimo_status": f"erro_http_{r.status_code}",
            "detalhe": None,
        }
    except Exception as exc:
        return {
            "online": False,
            "url": url,
            "contas_conectadas": cfg.get("contas_conectadas", 0),
            "ultimo_status": f"offline: {str(exc)[:200]}",
            "detalhe": None,
        }


@app.post("/api/flow-agent/image")
def flow_agent_image_route(body: FlowAgentImageBody):
    """Gera imagem via Flow Agent (servidor local com extensão Chrome)."""
    cfg = _flow_agent_config()
    if not cfg.get("ativo"):
        raise HTTPException(status_code=400, detail="Flow Agent não está ativado. Configure em Chaves de API.")
    url = cfg.get("url", "http://localhost:8001").rstrip("/")
    try:
        r = requests.post(f"{url}/api/v1/image", json={
            "prompt": body.prompt,
            "aspect": body.aspect,
            "count": body.count,
        }, timeout=300)
        if not r.ok:
            raise HTTPException(status_code=r.status_code, detail=f"Flow Agent erro {r.status_code}: {r.text[:200]}")
        return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao gerar imagem pelo Flow Agent: {str(exc)[:200]}")


@app.post("/api/flow-agent/video")
def flow_agent_video_route(body: FlowAgentVideoBody):
    """Gera vídeo via Flow Agent (servidor local com extensão Chrome)."""
    cfg = _flow_agent_config()
    if not cfg.get("ativo"):
        raise HTTPException(status_code=400, detail="Flow Agent não está ativado. Configure em Chaves de API.")
    url = cfg.get("url", "http://localhost:8001").rstrip("/")
    try:
        payload = {
            "prompt": body.prompt,
            "aspect": body.aspect,
            "duration": body.duration,
            "quality": body.quality,
        }
        if body.start_image:
            payload["start_image"] = body.start_image
        r = requests.post(f"{url}/api/v1/video", json=payload, timeout=1800)
        if not r.ok:
            raise HTTPException(status_code=r.status_code, detail=f"Flow Agent erro {r.status_code}: {r.text[:200]}")
        return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao gerar vídeo pelo Flow Agent: {str(exc)[:200]}")


# ------------------------------------------------------------------ vozes salvas
@app.get("/api/fish/saved-voices")
def get_saved_voices():
    return {"voices": nar.saved_fish_voices()}


@app.post("/api/login")
def login(body: LoginBody, request: Request):
    pwd = active_app_password()
    if not pwd:
        return {"ok": True, "message": "Proteção por senha não está ativada."}
    if not hmac.compare_digest(body.password, pwd):
        raise HTTPException(status_code=401, detail="Senha incorreta.")
    token = hashlib.sha256(pwd.encode()).hexdigest()
    response = JSONResponse({"ok": True})
    response.set_cookie("faceless_session", token, httponly=True, secure=(request.url.scheme == "https"), samesite="lax", max_age=60 * 60 * 24 * 14)
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("faceless_session")
    return response


@app.get("/api/catalog")
def catalog():
    return {
        "sources": providers.public_sources(), "templates": styles.public_templates(), "fonts": styles.FONT_CHOICES,
        "pacing": {k: v["label"] for k, v in styles.PACING.items()},
        "motions": {k: {"label": v["label"], "hint": v.get("hint", "")} for k, v in styles.MOTIONS.items()},
        "transitions": {k: {"label": v["label"], "mode": v.get("mode", "cut")} for k, v in styles.TRANSITIONS.items()},
        "effects": {k: {"label": v["label"], "hint": v.get("hint", "")} for k, v in styles.EFFECTS.items()},
        "cta_styles": {k: {"label": v.get("label", k.title()), "palette": v} for k, v in styles.CTA_STYLES.items()},
        "cta_texts": {k: {"main": v[0], "sub": v[1]} for k, v in styles.CTA_TEXTS.items()},
        "stages": [{"key": k, "label": label} for k, label in __import__("store").STAGES],
        "flow": {"ready": flow.is_ready(), "image_model": flow.IMAGE_MODEL, "video_model": flow.VIDEO_MODEL},
        "groq": {
            "ready": groq_transcribe.has_key(), "models": groq_transcribe.MODELS,
            "languages": groq_transcribe.LANGUAGES, "guidance": groq_transcribe.guidance(),
            "max_upload_mb": round(groq_transcribe.MAX_UPLOAD / 1024 / 1024, 1),
            "max_active": groq_transcribe.MAX_ACTIVE_JOBS,
        },
    }


@app.get("/api/flow/models")
def flow_models():
    try:
        return {"models": flow.list_models(), "image_model": flow.IMAGE_MODEL, "video_model": flow.VIDEO_MODEL}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ------------------------------------------------------------------ Skills de Roteiro

class SkillGenerateBody(BaseModel):
    skill_id: str
    topic: str
    language: str = "pt-BR"
    char_count: int | None = None


@app.get("/api/skills")
def list_skills():
    """Lista todas as skills de roteiro disponíveis."""
    try:
        skills_list = skills.load_skills()
        return {
            "skills": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "description": s["description"],
                    "category": s["category"],
                    "has_method": s["has_method"],
                    "script_template": s["script_template"],
                }
                for s in skills_list
            ],
            "total": len(skills_list),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/skills/{skill_id}")
def get_skill(skill_id: str):
    """Devolve os detalhes de uma skill específica."""
    skill = skills.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' não encontrada.")
    return skill


@app.post("/api/skills/generate")
def generate_skill_script(body: SkillGenerateBody):
    """Gera um roteiro usando uma skill selecionada."""
    try:
        result = skills.generate_narration_from_skill(
            skill_id=body.skill_id,
            topic=body.topic,
            language=body.language,
            char_count=body.char_count,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------ Skills de Roteiro como Estilos de Vídeo

class SkillStyleBody(BaseModel):
    skill_id: str


@app.get("/api/skills-video")
def list_skills_video():
    """Lista todas as skills disponíveis como estilos de vídeo para edição."""
    try:
        estilos_list = skills_video.load_skills_estilo()
        return {
            "skills": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "descricao": s["descricao"],
                    "categoria": s["categoria"],
                    "pasta": s["pasta"],
                    "estilo": s["estilo"],
                    "tem_metodo": s["tem_metodo"],
                    "tem_roteiro": s["tem_roteiro"],
                }
                for s in estilos_list
            ],
            "total": len(estilos_list),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/skills-video/{skill_id}")
def get_skill_video(skill_id: str):
    """Devolve o estilo de vídeo de uma skill específica."""
    estilo = skills_video.get_estilo_skill(skill_id)
    if not estilo:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' não encontrada.")
    return estilo


class ApplySkillStyleBody(BaseModel):
    skill_id: str
    project_id: str | None = None


@app.post("/api/skills-video/apply")
def apply_skill_style(body: ApplySkillStyleBody):
    """Aplica o estilo de vídeo de uma skill no projeto aberto.

    Sem projeto aberto, salva o estilo como padrão do estúdio, para que os
    próximos projetos já comecem com ele.
    """
    estilo = skills_video.get_estilo_skill(body.skill_id)
    if not estilo:
        raise HTTPException(status_code=404, detail=f"Skill '{body.skill_id}' não encontrada.")
    overrides = styles.sanitize_overrides(estilo.get("estilo") or {})
    nome = estilo.get("name") or body.skill_id

    project_id = (body.project_id or "").strip()
    if project_id:
        state = read_state(project_id)
        if project_id in ACTIVE_JOBS or state.get("status") in ("rendering", "searching", "queued_render"):
            raise HTTPException(status_code=409, detail="Aguarde o robô terminar para mudar o estilo.")

        def fn(s: dict[str, Any]) -> None:
            settings = s.setdefault("settings", {})
            settings["style"] = {**(settings.get("style") or {}), **overrides}

        patch_state(project_id, fn)
        return {
            "ok": True, "skill_id": body.skill_id, "skill_name": nome,
            "estilo": overrides, "applied_to": "project", "project_id": project_id,
        }

    project_config.update_system_config({"estilo_video_padrao": overrides})
    return {
        "ok": True, "skill_id": body.skill_id, "skill_name": nome,
        "estilo": overrides, "applied_to": "default",
    }


# ------------------------------------------------------------------ narração (Fish Audio)

@app.get("/api/fish/voices")
def list_fish_voices():
    if not os.getenv("FISH_API_KEY", "").strip():
        raise HTTPException(status_code=400, detail="Configure FISH_API_KEY no arquivo .env (aba Chaves de API).")
    try:
        return {"voices": nar.fish_voice_models(providers.provider_key("FISH_API_KEY", "Fish Audio"))}
    except requests.HTTPError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=f"Não foi possível listar suas vozes Fish Audio: {detail}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar vozes Fish Audio: {exc}")


@app.post("/api/fish/preview")
def fish_voice_preview(body: FishPreviewBody):
    if not os.getenv("FISH_API_KEY", "").strip():
        raise HTTPException(status_code=400, detail="Configure FISH_API_KEY no arquivo .env (aba Chaves de API).")
    text = body.text.strip()[:900]
    if not text:
        raise HTTPException(status_code=400, detail="Digite uma frase curta para testar a voz.")
    try:
        content = nar.fish_tts_bytes(text, body.reference_id.strip() if body.reference_id else None, body.model, providers.provider_key("FISH_API_KEY", "Fish Audio"))
        return Response(content=content, media_type="audio/mpeg", headers={"Cache-Control": "no-store", "Content-Disposition": 'inline; filename="fish-preview.mp3"'})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/narrations")
def create_narration(body: NarrationCreateBody, background_tasks: BackgroundTasks):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Cole o roteiro antes de gerar a narração.")
    if len(text) > 100000:
        raise HTTPException(status_code=413, detail="O roteiro excede 100.000 caracteres nesta versão.")
    if not os.getenv("FISH_API_KEY", "").strip():
        raise HTTPException(status_code=400, detail="Configure FISH_API_KEY no arquivo .env (aba Chaves de API).")
    model = body.model if body.model in {"s2.1-pro-free", "s2.1-pro", "s2-pro"} else "s2.1-pro-free"
    speed = max(0.5, min(2.0, body.speed))
    stability = max(0.0, min(1.0, body.stability))
    expressiveness = max(0.0, min(1.0, body.expressiveness))
    max_concurrent = max(1, min(8, body.max_concurrent))
    result = nar.create_job(
        text=text,
        reference_id=body.reference_id,
        model=model,
        speed=speed,
        stability=stability,
        expressiveness=expressiveness,
        max_concurrent=max_concurrent,
    )
    background_tasks.add_task(nar._run_generation, result["id"])
    return result


@app.get("/api/narrations/{job_id}")
def get_narration(job_id: str):
    return nar.get_job(job_id)


@app.get("/api/narrations/{job_id}/blocks")
def get_narration_blocks(job_id: str):
    """Retorna o status detalhado de cada bloco de narração."""
    return {"blocks": nar.get_block_status(job_id)}


@app.post("/api/narrations/{job_id}/pause")
def pause_narration(job_id: str):
    nar.pause(job_id)
    return {"ok": True, "paused": True}


@app.post("/api/narrations/{job_id}/resume")
def resume_narration(job_id: str, background_tasks: BackgroundTasks):
    nar.resume(job_id, background_tasks)
    return {"ok": True, "paused": False}


@app.post("/api/narrations/{job_id}/redo")
def redo_narration(job_id: str, background_tasks: BackgroundTasks):
    nar.redo(job_id, background_tasks)
    return {"ok": True, "status": "queued"}


@app.post("/api/narrations/{job_id}/cancel")
def cancel_narration(job_id: str):
    """Cancela a geração de narração em andamento."""
    nar.cancel(job_id)
    return {"ok": True, "cancelled": True}


@app.post("/api/narrations/{job_id}/preview-block/{block_index}")
def preview_narration_block(job_id: str, block_index: int):
    """Retorna o áudio de um bloco específico para pré-visualização."""
    state = nar._read_job(job_id)
    blocks = state.get("blocks", [])
    if block_index < 0 or block_index >= len(blocks):
        raise HTTPException(status_code=404, detail="Bloco não encontrado.")
    block = blocks[block_index]
    if block.get("status") != "complete":
        raise HTTPException(status_code=409, detail="Bloco ainda não foi gerado.")
    chunk_file = nar._job_dir(job_id) / f"chunk_{block_index:03d}.mp3"
    if not chunk_file.exists():
        raise HTTPException(status_code=404, detail="Áudio do bloco não encontrado no disco.")
    return FileResponse(chunk_file, media_type="audio/mpeg", filename=f"bloco_{block_index:03d}.mp3")


@app.get("/api/narrations/{job_id}/download")
def download_narration(job_id: str):
    file_path = nar.get_audio_file(job_id)
    return FileResponse(file_path, media_type="audio/mpeg", filename="narracao_fish_audio.mp3")


@app.get("/api/narrations/{job_id}/subtitles")
def download_narration_srt(job_id: str):
    file_path = nar.get_srt_file(job_id)
    return FileResponse(file_path, media_type="application/x-subrip", filename="narracao_estimada.srt")


@app.get("/api/narrations/cache")
def list_narration_cache():
    """Lista blocos de narração em cache (para reaproveitamento)."""
    return {"cache": nar.cache.list_cached()}


@app.delete("/api/narrations/{job_id}/cache")
def clear_narration_cache(job_id: str):
    """Remove o cache de um job específico."""
    folder = nar._job_dir(job_id)
    for f in folder.glob("chunk_*.mp3"):
        f.unlink(missing_ok=True)
    return {"ok": True, "message": "Cache do job limpo."}


# ------------------------------------------------------------------ proxy narração (Node.js DarkCut)
# Estas rotas encaminham para o servidor Node.js (server-narration.js, porta 3115)
# Use-as se preferir o motor Node.js em vez do motor Python (narration_engine.py).

class NarrationProxyCreateBody(BaseModel):
    text: str
    reference_id: str | None = None
    model: str = "s2.1-pro-free"
    speed: float = 1.0
    stability: float = 0.5
    expressiveness: float = 0.5
    max_concurrent: int = 4


@app.post("/api/narrations-proxy")
async def create_narration_proxy_route(body: NarrationProxyCreateBody):
    """Cria narração via servidor Node.js (DarkCut)."""
    return await nar_proxy.create_narration_proxy(
        text=body.text,
        reference_id=body.reference_id,
        model=body.model,
        speed=body.speed,
        stability=body.stability,
        expressiveness=body.expressiveness,
        max_concurrent=body.max_concurrent,
    )


@app.get("/api/narrations-proxy/{job_id}")
async def get_narration_proxy_route(job_id: str):
    """Consulta status de narração via Node.js."""
    return await nar_proxy.get_narration_status_proxy(job_id)


@app.delete("/api/narrations-proxy/{job_id}")
async def cancel_narration_proxy_route(job_id: str):
    """Cancela narração via Node.js."""
    return await nar_proxy.cancel_narration_proxy(job_id)


@app.get("/api/narrations-proxy/{job_id}/download")
async def download_narration_proxy_route(job_id: str):
    """Baixa áudio via Node.js."""
    return await nar_proxy.download_narration_proxy(job_id)


@app.get("/api/narrations-proxy/health")
async def health_narration_proxy():
    """Saúde do servidor Node.js de narração."""
    return await nar_proxy.get_narration_health_proxy()


@app.on_event("shutdown")
async def shutdown_narration_proxy():
    await nar_proxy.close_client()


# ------------------------------------------------------------------ motion graphics (Remotion)
MOTION_DIR = Path(__file__).resolve().parent / "data" / "motion"
MOTION_DIR.mkdir(parents=True, exist_ok=True)

class MotionRenderBody(BaseModel):
    text: str
    duration: float = 5.0
    width: int = 1920
    height: int = 1080
    cor_primaria: str = "#2F6FED"
    estilo: str = "documentario"


@app.post("/api/motion/render")
def render_motion_scene(body: MotionRenderBody):
    """Renderiza uma cena com Remotion e devolve a URL do MP4."""
    try:
        result = motion_render.render_scene(
            text=body.text,
            duration=body.duration,
            width=body.width,
            height=body.height,
            cor_primaria=body.cor_primaria,
            estilo=body.estilo,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/motion/{filename}")
def get_motion_video(filename: str):
    """Serve um vídeo renderizado pelo Remotion."""
    file_path = MOTION_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)


# ------------------------------------------------------------------ transcrição Groq (Whisper)

def _transcribe_language(value: str) -> str:
    allowed = {item["id"] for item in groq_transcribe.LANGUAGES}
    return value if value in allowed else "auto"


def _transcribe_mode(value: str) -> str:
    return value if value in groq_transcribe.ALLOWED_MODES else "auto"


async def _script_text_from_upload(upload: UploadFile | None) -> str:
    if not upload or not upload.filename:
        return ""
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in (".txt", ".md", ".srt"):
        raise HTTPException(status_code=400, detail="O roteiro deve ser um arquivo TXT, Markdown ou SRT.")
    raw = await upload.read(400_000)
    return groq_transcribe._clean_script(raw.decode("utf-8-sig", errors="replace"))[:200000]


@app.post("/api/transcribe")
async def start_transcription(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    script: UploadFile | None = File(None),
    script_text: str = Form(""),
    model: str = Form(groq_transcribe.DEFAULT_MODEL),
    language: str = Form("auto"),
    mode: str = Form("auto"),
):
    """Transcreve uma narração avulsa e devolve SRT/TXT/JSON sincronizados."""
    if not groq_transcribe.has_key():
        raise HTTPException(status_code=400, detail="Configure GROQ_API_KEY na tela de Chaves para transcrever.")
    if groq_transcribe.active_count() >= groq_transcribe.MAX_ACTIVE_JOBS:
        raise HTTPException(status_code=429, detail="Já existem duas transcrições em andamento. Aguarde a conclusão.")
    suffix = Path(audio.filename or "narracao.mp3").suffix.lower()
    if suffix not in groq_transcribe.AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Formato não suportado. Envie MP3, WAV, M4A, OGG, FLAC ou WebM.")
    text = (await _script_text_from_upload(script) or groq_transcribe._clean_script(script_text))[:200000]

    uploads = groq_transcribe.JOBS_DIR / "_uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    temp = uploads / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with temp.open("wb") as handle:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > groq_transcribe.MAX_UPLOAD:
                    raise HTTPException(status_code=413, detail=f"Áudio acima de {groq_transcribe.MAX_UPLOAD // (1024 * 1024)} MB.")
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="O arquivo de áudio está vazio.")
        job_id = groq_transcribe.create_job(
            temp, model=model, language=_transcribe_language(language), script_text=text,
            mode=_transcribe_mode(mode), origin="upload", name=audio.filename or temp.name,
        )
    finally:
        temp.unlink(missing_ok=True)
    background_tasks.add_task(groq_transcribe.run_job, job_id)
    return {"id": job_id, "status": "queued", "message": "Áudio recebido. A transcrição roda em segundo plano."}


@app.get("/api/transcribe")
def list_transcriptions(limit: int = 12):
    return {
        "jobs": groq_transcribe.list_jobs(limit),
        "ready": groq_transcribe.has_key(),
        "guidance": groq_transcribe.guidance(),
    }


@app.get("/api/transcribe/{job_id}")
def transcription_status(job_id: str):
    try:
        state = groq_transcribe.read_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=404, detail="Tarefa de transcrição não encontrada.")
    return groq_transcribe.public_job(state)


@app.get("/api/transcribe/{job_id}/download/{kind}")
def transcription_download(job_id: str, kind: str):
    if kind not in ("srt", "script_srt", "txt", "json"):
        raise HTTPException(status_code=404, detail="Formato de download não encontrado.")
    try:
        state = groq_transcribe.read_job(job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Tarefa de transcrição não encontrada.")
    if state.get("status") != "complete":
        raise HTTPException(status_code=409, detail="A transcrição ainda não está pronta.")
    files = {"srt": "legendas.srt", "script_srt": "roteiro.srt", "txt": "transcricao.txt", "json": "transcricao.json"}
    path = groq_transcribe.job_dir(job_id) / files[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Este arquivo não foi gerado para esta transcrição.")
    media = {"srt": "application/x-subrip", "script_srt": "application/x-subrip", "txt": "text/plain; charset=utf-8", "json": "application/json"}[kind]
    filename = f"legendas_groq.{ 'srt' if kind in ('srt', 'script_srt') else kind }"
    return FileResponse(path, media_type=media, filename=filename, headers={"Cache-Control": "no-store"})


@app.post("/api/projects/{project_id}/transcribe")
async def transcribe_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    model: str = Form(groq_transcribe.DEFAULT_MODEL),
    language: str = Form("auto"),
    mode: str = Form("auto"),
    use_script: str = Form("true"),
):
    """Melhora as legendas de um projeto já criado usando a narração real."""
    if not groq_transcribe.has_key():
        raise HTTPException(status_code=400, detail="Configure GROQ_API_KEY na tela de Chaves para transcrever.")
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("searching", "rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar a etapa atual antes de transcrever.")
    if groq_transcribe.active_count() >= groq_transcribe.MAX_ACTIVE_JOBS:
        raise HTTPException(status_code=429, detail="Já existem duas transcrições em andamento. Aguarde a conclusão.")
    audio = project_dir(project_id) / (state.get("audio_file") or "narration.mp3")
    if not audio.exists():
        raise HTTPException(status_code=404, detail="O áudio da narração não foi encontrado no projeto.")

    text = ""
    if use_script.strip().lower() not in ("0", "false", "no", "off") and state.get("script_file"):
        script_path = project_dir(project_id) / state["script_file"]
        if script_path.exists():
            text = groq_transcribe._clean_script(script_path.read_text(encoding="utf-8-sig", errors="replace"))[:200000]

    job_id = groq_transcribe.create_job(
        audio, model=model, language=_transcribe_language(language), script_text=text,
        mode=_transcribe_mode(mode), origin="project", project_id=project_id,
        name=state.get("title") or "projeto", seconds=float(state.get("audio_duration") or 0),
    )
    background_tasks.add_task(groq_transcribe.run_job, job_id)
    return {"id": job_id, "status": "queued", "project_id": project_id,
            "message": "Transcrição iniciada. As legendas do projeto serão atualizadas quando terminar."}


# ------------------------------------------------------------------ biblioteca de música

def _music_meta(music_id: str) -> dict[str, Any]:
    meta = MUSIC_DIR / f"{music_id}.json"
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Música não encontrada na biblioteca.")


@app.get("/api/music")
def list_music():
    items = []
    for meta in MUSIC_DIR.glob("*.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            if music_path({"music_id": data["id"]}):
                items.append(data)
        except Exception:
            continue
    items.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return items


@app.post("/api/music")
async def upload_music(file: UploadFile = File(...)):
    suffix = Path(file.filename or "musica.mp3").suffix.lower()
    if suffix not in AUDIO_EXT:
        raise HTTPException(status_code=400, detail=f"Formato não suportado ({suffix or 'sem extensão'}). Envie MP3, WAV, M4A, AAC ou OGG.")
    music_id = uuid.uuid4().hex[:12]
    dest = MUSIC_DIR / f"{music_id}{suffix}"
    size = 0
    with dest.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > 120 * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Música acima de 120 MB.")
            handle.write(chunk)
    try:
        duration = media_duration(dest)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))
    meta = {"id": music_id, "name": Path(file.filename or "musica").stem[:80], "duration": round(duration, 1), "size_mb": round(size / 1024 / 1024, 1), "created_at": now_iso(), "url": f"/api/music/{music_id}/file"}
    (MUSIC_DIR / f"{music_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


@app.get("/api/music/{music_id}/file")
def music_file(music_id: str):
    path = music_path({"music_id": music_id})
    if not path:
        raise HTTPException(status_code=404, detail="Música não encontrada na biblioteca.")
    return FileResponse(path)


@app.delete("/api/music/{music_id}")
def delete_music(music_id: str):
    path = music_path({"music_id": music_id})
    _music_meta(music_id)
    if path:
        path.unlink(missing_ok=True)
    (MUSIC_DIR / f"{music_id}.json").unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/mix-preview")
async def mix_preview(settings: str = Form("{}"), project_id: str | None = Form(None), narration: UploadFile | None = File(None)):
    """Gera 20 s do mix (narração + música) com o mesmo filtro do render, para ajustar o volume de ouvido."""
    try:
        raw = json.loads(settings or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Configuração inválida.")
    audio = normalize_settings({"audio": raw.get("audio", raw)})["audio"]
    tmp = Path(tempfile.mkdtemp(prefix="mix_", dir=PREVIEW_DIR))
    try:
        if narration and narration.filename:
            src = tmp / ("narr" + (Path(narration.filename).suffix.lower() or ".mp3"))
            with src.open("wb") as handle:
                while chunk := await narration.read(1024 * 1024):
                    handle.write(chunk)
        elif project_id:
            state = read_state(project_id)
            src = project_dir(project_id) / state["audio_file"]
        else:
            raise HTTPException(status_code=400, detail="Escolha o arquivo de narração para testar o mix.")
        music = music_path(audio)
        if not music:
            raise HTTPException(status_code=400, detail="Escolha uma música da biblioteca para testar o mix.")
        total = media_duration(src)
        seconds = min(20.0, total)
        out = tmp / "preview.mp3"
        run_ffmpeg(build_mix_cmd(src, music, audio, out, seconds, fmt="mp3"), timeout=120)
        return Response(content=out.read_bytes(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:400])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ prévia real do estilo

def _preview_image(project_id: str | None, scene_id: str | None) -> Path:
    sample = BASE_DIR / "static" / "sample" / "frame.jpg"
    if not project_id:
        return sample
    try:
        state = read_state(project_id)
        folder = project_dir(project_id)
        scenes = state.get("scenes", [])
        scene = next((s for s in scenes if s["id"] == scene_id), None) or next((s for s in scenes if s.get("options")), None)
        if not scene:
            return sample
        option = scene["options"][min(int(scene.get("selected", 0)), len(scene["options"]) - 1)]
        if option.get("local_file") and (folder / option["local_file"]).exists():
            return folder / option["local_file"]
        if scene.get("media_file") and (folder / scene["media_file"]).exists():
            return folder / scene["media_file"]
        thumb = option.get("thumbnail", "")
        if thumb.startswith("http"):
            cache = PREVIEW_DIR / f"thumb_{hashlib.sha1(thumb.encode()).hexdigest()[:16]}.jpg"
            if not cache.exists():
                r = requests.get(thumb, timeout=20, headers={"User-Agent": "FacelessCloudStudio/0.4"})
                r.raise_for_status()
                cache.write_bytes(r.content)
            return cache
    except Exception:
        pass
    return sample


@app.get("/api/styles/preview")
def style_preview(template: str = styles.DEFAULT_TEMPLATE, ratio: str = "16:9", text: str = "A cidade que o mercado esqueceu",
                  overrides: str = "{}", project_id: str | None = None, scene_id: str | None = None):
    try:
        ov = json.loads(overrides or "{}")
    except json.JSONDecodeError:
        ov = {}
    if ratio not in ("16:9", "9:16", "1:1"):
        ratio = "16:9"
    try:
        image = _preview_image(project_id, scene_id)
        path = styles.render_preview(image, styles.resolve_style(template, ov), ratio, text[:140] or "Legenda de exemplo")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não consegui gerar a prévia: {str(exc)[:200]}")


# ------------------------------------------------------------------ projetos

def _public_project(state: dict[str, Any]) -> dict[str, Any]:
    return state


def _status_payload(state: dict[str, Any], since: int) -> dict[str, Any]:
    return {
        "id": state.get("id"), "status": state.get("status"), "progress": state.get("progress", 0), "message": state.get("message", ""),
        "error": state.get("error"), "stages": state.get("stages", {}), "current_stage": state.get("current_stage"),
        "log": [e for e in state.get("log", []) if e["n"] > since], "log_seq": state.get("log_seq", 0),
        "scenes_rev": state.get("scenes_rev", 0), "capcut": state.get("capcut", {"status": "none"}),
        "output_file": state.get("output_file"), "updated_at": state.get("updated_at"), "render_started": state.get("render_started"),
        "generating": any((s.get("gen") or {}).get("status") == "running" for s in state.get("scenes", [])),
    }


async def _save_upload(upload: UploadFile, folder: Path, base: str, allowed: tuple[str, ...]) -> str:
    suffix = Path(upload.filename or base).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Formato não suportado: {suffix or 'sem extensão'}.")
    filename = base + suffix
    dest = folder / filename
    size = 0
    with dest.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Arquivo acima do limite de {MAX_UPLOAD_MB} MB.")
            handle.write(chunk)
    return filename


@app.post("/api/projects")
async def create_project(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    settings: str = Form("{}"),
    script: UploadFile | None = File(None),
    narration: UploadFile = File(...),
    subtitles: UploadFile = File(...),
):
    title = title.strip()[:100]
    if not title:
        raise HTTPException(status_code=400, detail="Informe um nome para o projeto.")
    try:
        cfg = normalize_settings(json.loads(settings or "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Configurações inválidas.")
    if not cfg.get("style"):
        try:
            padrao = project_config.load_system_config().get("estilo_video_padrao") or {}
        except Exception:
            padrao = {}
        if isinstance(padrao, dict) and padrao:
            cfg["style"] = styles.sanitize_overrides(padrao)
    if not cfg["sources"]:
        raise HTTPException(status_code=400, detail="Selecione pelo menos uma fonte de mídia na aba Mídia.")
    if cfg["audio"]["music_id"] and not music_path(cfg["audio"]):
        cfg["audio"]["music_id"] = None

    pid = uuid.uuid4().hex
    folder = DATA_DIR / pid
    folder.mkdir(parents=True, exist_ok=True)
    try:
        audio_name = await _save_upload(narration, folder, "narration", AUDIO_EXT)
        srt_name = await _save_upload(subtitles, folder, "subtitles", (".srt",))
        script_name = await _save_upload(script, folder, "script", (".txt", ".md")) if script and script.filename else None
        srt_content = (folder / srt_name).read_text(encoding="utf-8-sig", errors="replace")
        cues = parse_srt(srt_content)
        (folder / srt_name).write_text(srt_content, encoding="utf-8")
        lang = cfg["search_lang"]
        if lang == "auto":
            from scenes import detect_lang
            lang = detect_lang(" ".join(c["text"] for c in cues[:60]))
        scenes, capped = group_cues(cues, cfg["pacing"], lang, cfg["query_extra"], MAX_SCENES)
        audio_len = media_duration(folder / audio_name)
        stages = default_stages()
        stages["input"].update({"status": "done", "detail": f"Narração de {int(audio_len // 60)}:{int(audio_len % 60):02d}", "progress": 100, "ended": now_iso()})
        stages["parse"].update({"status": "done", "detail": f"{len(cues)} legendas em {len(scenes)} cenas", "progress": 100, "ended": now_iso()})
        log = [
            {"n": 1, "t": now_iso(), "stage": "input", "level": "info", "msg": f"Arquivos recebidos: narração de {audio_len:.0f} s e {len(cues)} legendas."},
            {"n": 2, "t": now_iso(), "stage": "parse", "level": "info", "msg": f"Dividi em {len(scenes)} cenas (ritmo {styles.PACING[cfg['pacing']]['label'].lower()}, busca em {'inglês' if lang == 'en' else 'português'})."},
        ]
        if capped:
            log.append({"n": 3, "t": now_iso(), "stage": "parse", "level": "warn", "msg": f"O ritmo escolhido passava de {MAX_SCENES} cenas; juntei cenas vizinhas para respeitar o limite (MAX_SCENES)."})
        state = {
            "id": pid, "title": title, "created_at": now_iso(), "updated_at": now_iso(), "status": "queued", "progress": 0,
            "message": "Projeto recebido. Preparando a busca de cenas...", "settings": cfg, "ratio": cfg["ratio"], "quality": cfg["quality"],
            "audio_file": audio_name, "srt_file": srt_name, "script_file": script_name, "cue_count": len(cues), "audio_duration": round(audio_len, 2),
            "scenes": scenes, "scenes_rev": 0, "stages": stages, "log": log, "log_seq": len(log), "capcut": {"status": "none"}, "error": None,
        }
        write_state(pid, state)
        background_tasks.add_task(analyze_project, pid)
        return {"id": pid, "title": title, "status": "queued", "scene_count": len(scenes)}
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


@app.get("/api/projects")
def list_projects():
    result = []
    for folder in DATA_DIR.iterdir():
        state_file = folder / "project.json"
        if folder.is_dir() and state_file.exists():
            try:
                d = json.loads(state_file.read_text(encoding="utf-8"))
                st = d.get("settings", {})
                result.append({"id": d.get("id"), "title": d.get("title"), "status": d.get("status"), "progress": d.get("progress", 0), "message": d.get("message"),
                               "created_at": d.get("created_at"), "ratio": st.get("ratio", d.get("ratio")), "template": st.get("template"),
                               "scenes": len(d.get("scenes", [])), "duration": d.get("audio_duration")})
            except Exception:
                continue
    result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return result[:40]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return _public_project(read_state(project_id))


@app.get("/api/projects/{project_id}/status")
def get_status(project_id: str, since: int = 0):
    return _status_payload(read_state(project_id), since)


# ------------------------------------------------------------------ MCP interno (chat da interface)

class McpCallBody(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


@app.post("/api/mcp/call")
def mcp_call_route(body: McpCallBody):
    """Executa as ferramentas usadas pelo chat MCP embutido na interface do Flow."""
    tool = (body.tool or "").strip()
    args = body.arguments or {}

    if tool in ("list_projects", "list_studio_projects"):
        rows = list_projects()
        projects = [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "status": p.get("status"),
                "scenes": p.get("scenes", 0),
                "progress": p.get("progress", 0),
            }
            for p in rows
        ]
        return {"total": len(projects), "projects": projects}

    if tool == "suggest_media_for_script":
        project_id = str(args.get("project_id") or "").strip()
        if not project_id:
            raise HTTPException(status_code=400, detail="Informe o project_id.")
        try:
            max_blocks = max(1, min(int(args.get("max_blocks") or 60), 200))
        except (TypeError, ValueError):
            max_blocks = 60
        state = read_state(project_id)
        sugestoes = []
        for idx, scene in enumerate((state.get("scenes") or [])[:max_blocks]):
            texto = str(scene.get("text") or "").strip()
            if not texto:
                continue
            sugestoes.append({
                "index": idx,
                "texto": texto[:400],
                "has_options": bool(scene.get("options")),
                "image_query": scene.get("query") or make_query(texto),
                "video_query": make_youtube_query(texto),
            })
        return {
            "title": state.get("title") or "sem título",
            "project_id": project_id,
            "total_scenes": len(sugestoes),
            "sugestoes": sugestoes,
        }

    if tool in ("generate_image_prompt", "generate_video_prompt"):
        scene_text = str(args.get("scene_text") or "").strip()
        if not scene_text:
            raise HTTPException(status_code=400, detail="Informe o texto da cena.")
        plano = scene_planner.gerar_consultas_para_cena(scene_text)
        consultas = [c for c in (plano.get("consultas") or []) if c]
        descricao = plano.get("descricao_visual") or scene_text[:160]
        base = consultas[0] if consultas else descricao
        if tool == "generate_image_prompt":
            style = str(args.get("style") or "cinematic")
            estilo_txt = {
                "cinematic": "cinematic lighting, dramatic composition, film still, ultra detailed, 4k",
                "realistic": "photorealistic, natural light, sharp focus, high detail, 4k",
                "anime": "anime style, 2D illustration, clean line art, vibrant colors",
                "minimal": "minimalist composition, negative space, soft light, clean background",
            }.get(style, "cinematic lighting, ultra detailed, 4k")
            return {
                "style": style,
                "prompt": f"{base}, {estilo_txt}",
                "descricao_visual": descricao,
                "consultas": consultas,
            }
        duration = args.get("duration") or 6
        return {
            "prompt": f"{base} — moving camera, natural motion, {duration}s, cinematic 4k",
            "descricao_visual": descricao,
            "consultas": consultas,
            "duration": duration,
        }

    raise HTTPException(status_code=404, detail=f"Ferramenta MCP '{tool}' não encontrada.")


@app.patch("/api/projects/{project_id}/settings")
def update_settings(project_id: str, body: dict[str, Any]):
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("rendering", "searching", "queued_render"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar para mudar as configurações.")
    merged = normalize_settings(body, state.get("settings"))
    if merged["audio"]["music_id"] and not music_path(merged["audio"]):
        merged["audio"]["music_id"] = None

    def fn(s: dict[str, Any]) -> None:
        s["settings"] = merged
        s["ratio"], s["quality"] = merged["ratio"], merged["quality"]
        if s.get("status") == "complete":
            s["settings_changed_after_render"] = True
    return {"settings": patch_state(project_id, fn)["settings"]}


def _find_scene(state: dict[str, Any], scene_id: str) -> dict[str, Any]:
    for scene in state.get("scenes", []):
        if scene.get("id") == scene_id:
            return scene
    raise HTTPException(status_code=404, detail="Cena não encontrada.")


@app.patch("/api/projects/{project_id}/scenes/{scene_id}")
def update_scene(project_id: str, scene_id: str, body: SceneUpdate):
    state = read_state(project_id)
    if state.get("status") in ("searching", "rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar a etapa atual.")
    scene = _find_scene(state, scene_id)
    if body.selected is not None and not (0 <= body.selected < len(scene.get("options", []))):
        raise HTTPException(status_code=400, detail="Opção de mídia inválida.")

    def fn(s: dict[str, Any]) -> None:
        sc = _find_scene(s, scene_id)
        if body.selected is not None:
            sc["selected"] = body.selected
        if body.query is not None and body.query.strip():
            sc["query"] = body.query.strip()[:160]
        s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
        if s.get("status") == "complete":
            s["settings_changed_after_render"] = True
    return {"ok": True, "scene": _find_scene(patch_state(project_id, fn), scene_id)}


@app.post("/api/projects/{project_id}/scenes/{scene_id}/search")
def research_scene(project_id: str, scene_id: str, body: SceneSearchBody):
    """Busca de novo uma cena, com texto e fontes escolhidos na hora."""
    state = read_state(project_id)
    if state.get("status") in ("searching", "rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar a etapa atual.")
    scene = _find_scene(state, scene_id)
    settings = state["settings"]
    query = (body.query or scene["query"]).strip()[:160]
    sources = [s for s in (body.sources or settings["sources"]) if s in providers.SOURCE_IDS]
    if not sources:
        raise HTTPException(status_code=400, detail="Selecione pelo menos uma fonte.")
    options, messages = providers.search_scene_assets(
        query, sources, {}, per=settings["per_source"],
        orientation=providers.orientation_for(settings["ratio"]), pref=settings["media_pref"],
        queries=query_variants(query, settings.get("search_lang", "auto"), settings.get("query_extra", ""), 3)[1:],
        smart=True,
    )
    keep = [o for o in scene.get("options", []) if o.get("local_file")]

    def fn(s: dict[str, Any]) -> None:
        sc = _find_scene(s, scene_id)
        sc["query"] = query
        sc["options"] = keep + options
        sc["selected"] = 0
        sc["status"] = "found" if (keep or options) else "empty"
        s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
    result = _find_scene(patch_state(project_id, fn), scene_id)
    return {"scene": result, "messages": messages}


@app.post("/api/projects/{project_id}/scenes/{scene_id}/upload")
async def upload_scene_media(project_id: str, scene_id: str, file: UploadFile = File(...)):
    state = read_state(project_id)
    folder = project_dir(project_id)
    _find_scene(state, scene_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in MEDIA_IMG + MEDIA_VID:
        raise HTTPException(status_code=400, detail="Envie uma imagem (JPG, PNG, WEBP) ou um vídeo (MP4, MOV, WEBM).")
    uploads = folder / "uploads"
    uploads.mkdir(exist_ok=True)
    name = f"{uuid.uuid4().hex[:10]}{suffix}"
    dest = uploads / name
    size = 0
    with dest.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_MEDIA_MB * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Arquivo acima do limite de {MAX_MEDIA_MB} MB.")
            handle.write(chunk)
    try:
        info = probe_media(dest)
        if not info["has_video"]:
            raise RuntimeError("O arquivo não tem imagem. Envie uma foto ou um vídeo válido.")
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))
    is_video = suffix in MEDIA_VID
    thumb_rel = f"uploads/{name}"
    if is_video:
        thumb = uploads / f"{name}.jpg"
        subprocess.run([ffmpeg_path(), "-y", "-ss", "0.3", "-i", str(dest), "-vf", "scale=480:-2", "-frames:v", "1", str(thumb)], capture_output=True, timeout=60)
        thumb_rel = f"uploads/{name}.jpg" if thumb.exists() else thumb_rel
    option = {
        "id": name, "provider": "Meu arquivo", "media_type": "video" if is_video else "image", "download_url": "", "local_file": f"uploads/{name}",
        "thumbnail": f"/api/projects/{project_id}/files/{thumb_rel.split('/', 1)[1]}", "source_url": "", "photographer": "Você",
        "license": "Arquivo enviado por você", "width": info["width"], "height": info["height"], "duration": info["duration"] if is_video else None,
    }

    def fn(s: dict[str, Any]) -> None:
        sc = _find_scene(s, scene_id)
        sc.setdefault("options", []).insert(0, option)
        sc["selected"] = 0
        sc["status"] = "found"
        s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
    return {"scene": _find_scene(patch_state(project_id, fn), scene_id)}


@app.get("/api/projects/{project_id}/files/{name}")
def project_file(project_id: str, name: str):
    folder = project_dir(project_id) / "uploads"
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(path)


@app.post("/api/projects/{project_id}/scenes/{scene_id}/generate")
def generate_scene_media(project_id: str, scene_id: str, body: GenerateBody, background_tasks: BackgroundTasks):
    """Gera uma imagem (Nano Banana) ou um clipe (Veo) com IA para a cena. Cobrado na sua chave da Gemini API."""
    if not flow.is_ready():
        raise HTTPException(status_code=400, detail=flow.readiness_error())
    state = read_state(project_id)
    scene = _find_scene(state, scene_id)
    if (scene.get("gen") or {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="Esta cena já está gerando mídia.")
    prompt = body.prompt.strip()
    if len(prompt) < 8:
        raise HTTPException(status_code=400, detail="Descreva a cena com pelo menos uma frase.")
    kind = "video" if body.kind == "video" else "image"
    seconds = body.seconds if body.seconds in (4, 6, 8) else 6

    def mark(s: dict[str, Any]) -> None:
        sc = _find_scene(s, scene_id)
        sc["gen"] = {"status": "running", "kind": kind, "message": "Enviando o pedido ao Google...", "started": now_iso()}
        s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
    patch_state(project_id, mark)
    background_tasks.add_task(_run_generation, project_id, scene_id, kind, prompt[:900], seconds)
    return {"ok": True, "status": "running"}


def _run_generation(pid: str, scene_id: str, kind: str, prompt: str, seconds: int) -> None:
    T = Tracker(pid)
    label = "Veo" if kind == "video" else "Nano Banana"
    try:
        state = read_state(pid)
        folder = project_dir(pid)
        ratio = state["settings"]["ratio"]
        uploads = folder / "uploads"
        uploads.mkdir(exist_ok=True)
        name = f"ia_{uuid.uuid4().hex[:8]}"
        T.log(f"Gerando {'vídeo' if kind == 'video' else 'imagem'} com {label} para a cena...", stage="search")

        def status(msg: str) -> None:
            patch_state(pid, lambda s: _find_scene(s, scene_id).setdefault("gen", {}).update({"message": msg}))
        if kind == "video":
            path = flow.generate_video(prompt, ratio, seconds, uploads / name, on_status=status)
        else:
            path = flow.generate_image(prompt, ratio, uploads / name)
        info = probe_media(path)
        thumb_rel = path.name
        if kind == "video":
            thumb = uploads / f"{path.name}.jpg"
            subprocess.run([ffmpeg_path(), "-y", "-ss", "0.3", "-i", str(path), "-vf", "scale=480:-2", "-frames:v", "1", str(thumb)], capture_output=True, timeout=60)
            thumb_rel = thumb.name if thumb.exists() else path.name
        option = {
            "id": path.name, "provider": f"Google Flow ({label})", "media_type": kind, "download_url": "", "local_file": f"uploads/{path.name}",
            "thumbnail": f"/api/projects/{pid}/files/{thumb_rel}", "source_url": "", "photographer": f"IA · {label}",
            "license": "Gerado por IA (marca SynthID)", "width": info["width"], "height": info["height"],
            "duration": info["duration"] if kind == "video" else None, "prompt": prompt,
        }

        def done(s: dict[str, Any]) -> None:
            sc = _find_scene(s, scene_id)
            sc.setdefault("options", []).insert(0, option)
            sc["selected"] = 0
            sc["status"] = "found"
            sc["gen"] = {"status": "done", "kind": kind, "message": f"{label} concluído."}
            s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
        patch_state(pid, done)
        T.log(f"{label}: mídia gerada e adicionada às opções da cena.", stage="search")
    except Exception as exc:
        msg = str(exc)[:400]

        def fail(s: dict[str, Any]) -> None:
            _find_scene(s, scene_id)["gen"] = {"status": "failed", "kind": kind, "message": msg}
            s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
        try:
            patch_state(pid, fail)
            T.log(f"{label} falhou: {msg}", "error", stage="search")
        except Exception:
            pass


@app.post("/api/projects/{project_id}/auto-pick")
def auto_pick_route(project_id: str):
    state = read_state(project_id)
    if state.get("status") in ("searching", "rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar a etapa atual.")

    def fn(s: dict[str, Any]) -> None:
        auto_pick(s["scenes"], s["settings"]["media_pref"], s["settings"]["ratio"])
        s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1
    patch_state(project_id, fn)
    return {"ok": True}


@app.post("/api/projects/{project_id}/research")
def research_all(project_id: str, background_tasks: BackgroundTasks):
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("searching", "rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="O robô já está trabalhando neste projeto.")
    patch_state(project_id, lambda s: s.update({"status": "searching", "message": "Preparando nova busca..."}))
    background_tasks.add_task(analyze_project, project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/research-empty")
def research_empty(project_id: str, background_tasks: BackgroundTasks):
    """Busca mídia apenas nas cenas que ainda não têm nenhuma opção (status='empty' ou options=[])."""
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("searching", "rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="O robô já está trabalhando neste projeto.")
    # Marca apenas as cenas vazias como 'pending' para a busca
    empty_ids = {s["id"] for s in state.get("scenes", []) if not s.get("options")}
    if not empty_ids:
        raise HTTPException(status_code=400, detail="Todas as cenas já têm mídia. Use 'Buscar tudo de novo' para refazer a busca completa.")
    patch_state(project_id, lambda s: s.update({"status": "searching", "message": f"Buscando mídia apenas nas {len(empty_ids)} cenas sem resultado..."}))
    background_tasks.add_task(analyze_empty_scenes, project_id, empty_ids)
    return {"ok": True, "empty_count": len(empty_ids)}


# ------------------------------------------------------------------ Módulo CENAS (filmagem real - cadeia de prioridade)

class ScenePlanBody(BaseModel):
    srt_text: str | None = None
    texto: str | None = None
    idioma: str = "auto"
    max_cenas: int = 60
    usar_llm: bool = True


class ScenePlanSearchBody(BaseModel):
    scene_id: str
    query: str | None = None
    provedor: str | None = None
    modo_busca: str = "padrao"  # padrao | moderado | severo


class ScenePickBody(BaseModel):
    scene_id: str
    provedor: str
    asset_id: str
    opcao_idx: int = 0


@app.post("/api/scenes/plan")
def scenes_plan(body: ScenePlanBody):
    """Divide um SRT/roteiro em cenas e gera consultas de busca para cada uma."""
    texto = body.srt_text or body.texto or ""
    if not texto.strip():
        raise HTTPException(status_code=400, detail="Informe um SRT ou roteiro.")
    cenas = scene_planner.planejar_cenas(
        texto, idioma=body.idioma, max_cenas=body.max_cenas, usar_llm=body.usar_llm
    )
    return {"cenas": cenas, "total": len(cenas)}


@app.post("/api/scenes/search")
async def scenes_search(body: ScenePlanSearchBody):
    """Busca mídia para uma cena específica usando cadeia de prioridade."""
    query = body.query or ""
    if not query:
        raise HTTPException(status_code=400, detail="Informe um termo de busca.")

    provedores_ordem = ["wikimedia", "nasa", "nara", "openverse", "pexels", "pixabay", "youtube"]
    if body.provedor:
        provedores_ordem = [body.provedor] + [p for p in provedores_ordem if p != body.provedor]

    resultados = []
    for nome in provedores_ordem:
        prov = media_providers.get_provider(nome)
        if not prov or not prov.is_ready():
            continue
        try:
            lista = await prov.search(query, per=6, media_type="video")
            for item in lista:
                resultados.append(item)
            if resultados:
                break  # para no primeiro provedor que atender (modo padrao)
        except Exception:
            continue

    if body.modo_busca == "severo" and not resultados:
        return {"resultados": [], "total": 0, "para_conferir": True, "mensagem": "Nenhum resultado aceitável em modo severo."}

    return {"resultados": resultados, "total": len(resultados)}


@app.post("/api/projects/{project_id}/scenes/plan-from-srt")
def scenes_plan_from_srt(project_id: str, body: ScenePlanBody):
    """Planeja cenas a partir do SRT de um projeto e salva no estado."""
    state = read_state(project_id)
    srt_name = state.get("srt_file")
    if not srt_name:
        raise HTTPException(status_code=400, detail="O projeto não tem SRT associado.")
    srt_path = project_dir(project_id) / srt_name
    if not srt_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo SRT não encontrado no projeto.")
    srt_text = srt_path.read_text(encoding="utf-8-sig", errors="replace")
    cenas = scene_planner.planejar_cenas(
        srt_text, idioma=body.idioma, max_cenas=body.max_cenas, usar_llm=body.usar_llm
    )
    def fn(s: dict[str, Any]) -> None:
        s.setdefault("cenas_planejadas", cenas)
        s["cenas_planejadas_total"] = len(cenas)
        s["cenas_planejadas_idioma"] = body.idioma
        s["updated_at"] = now_iso()
    patch_state(project_id, fn)
    return {"cenas": cenas, "total": len(cenas)}


@app.get("/api/projects/{project_id}/scenes/plan")
def scenes_get_plan(project_id: str):
    """Devolve as cenas planejadas de um projeto."""
    state = read_state(project_id)
    return {"cenas": state.get("cenas_planejadas", []), "total": state.get("cenas_planejadas_total", 0)}


@app.post("/api/projects/{project_id}/scenes/pick-from-provider")
def scenes_pick_from_provider(project_id: str, body: ScenePickBody):
    """Escolhe um asset de um provedor para uma cena (registra licença para créditos)."""
    state = read_state(project_id)

    def fn(s: dict[str, Any]) -> None:
        cenas = s.setdefault("cenas_escolhidas", [])
        for c in cenas:
            if c.get("scene_id") == body.scene_id:
                c.update({"provedor": body.provedor, "asset_id": body.asset_id, "opcao_idx": body.opcao_idx, "status": "selecionado"})
                break
        else:
            cenas.append({"scene_id": body.scene_id, "provedor": body.provedor, "asset_id": body.asset_id, "opcao_idx": body.opcao_idx, "status": "selecionado"})
        s["updated_at"] = now_iso()
    patch_state(project_id, fn)
    return {"ok": True}


@app.get("/api/providers/media")
def list_media_providers_route():
    """Devolve o status de cada provedor de mídia."""
    return {"providers": [p.public_meta() for p in media_providers.PROVIDERS]}


@app.post("/api/projects/{project_id}/scenes/buscar-cadeia")
async def scenes_buscar_cadeia(project_id: str, body: SceneSearchBody):
    """Busca mídia para uma cena usando a cadeia de prioridade configurada no projeto."""
    state = read_state(project_id)
    cfg = state.get("settings", {})
    cenas_config = cfg.get("cenas", {}) if isinstance(cfg, dict) else {}
    prioridade = cenas_config.get("prioridade", ["youtube_video", "youtube_clipe", "bancos", "ia"])
    bancos = cenas_config.get("bancos", ["wikimedia", "nasa", "nara", "openverse", "pexels", "pixabay"])
    somente_cc = cenas_config.get("youtube", {}).get("somente_creative_commons", True)
    modo_busca = cenas_config.get("modo_busca", "padrao")

    mapa_provedores = {
        "wikimedia": "wikimedia", "nasa": "nasa", "nara": "nara",
        "openverse": "openverse", "pexels": "pexels", "pixabay": "pixabay", "youtube": "youtube",
    }
    ordem = [mapa_provedores[b] for b in bancos if b in mapa_provedores and media_providers.get_provider(b).is_ready()]

    query = body.query or ""
    if not query:
        raise HTTPException(status_code=400, detail="Informe um termo de busca.")

    resultados = []
    for nome in ordem:
        prov = media_providers.get_provider(nome)
        if not prov:
            continue
        try:
            kwargs = {}
            if nome == "youtube":
                kwargs["somente_creative_commons"] = somente_cc
            lista = await prov.search(query, per=6, media_type="video", **kwargs)
            for item in lista:
                resultados.append(item)
            if modo_busca == "padrao" and resultados:
                break
        except Exception:
            continue

    severo = modo_busca == "severo"
    return {
        "resultados": resultados,
        "total": len(resultados),
        "para_conferir": severo and not resultados,
        "provedores_tentados": ordem,
    }


@app.post("/api/projects/{project_id}/render")
def start_render(project_id: str, background_tasks: BackgroundTasks):
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("rendering", "queued_render"):
        raise HTTPException(status_code=409, detail="Este projeto já está sendo montado.")
    if state.get("status") == "searching":
        raise HTTPException(status_code=409, detail="A busca de mídia ainda está em andamento.")
    if not any(s.get("options") for s in state.get("scenes", [])):
        raise HTTPException(status_code=400, detail="Nenhuma cena tem mídia. Ajuste as fontes e busque de novo, ou envie seus próprios arquivos.")

    def fn(s: dict[str, Any]) -> None:
        s.update({"status": "queued_render", "progress": 0, "message": "Montagem na fila...", "error": None, "cancel_requested": False, "settings_changed_after_render": False})
    patch_state(project_id, fn)
    background_tasks.add_task(run_render_job, project_id)
    return {"ok": True, "status": "queued_render"}


@app.post("/api/projects/{project_id}/cancel")
def cancel_job(project_id: str):
    state = read_state(project_id)
    if state.get("status") not in ("rendering", "queued_render", "searching") and project_id not in ACTIVE_JOBS:
        raise HTTPException(status_code=409, detail="Nada em andamento para cancelar.")
    patch_state(project_id, lambda s: s.update({"cancel_requested": True}))
    return {"ok": True}


@app.post("/api/projects/{project_id}/capcut")
def start_capcut(project_id: str, background_tasks: BackgroundTasks):
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("rendering", "queued_render", "searching"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar para exportar o projeto do CapCut.")
    if not any(s.get("options") for s in state.get("scenes", [])):
        raise HTTPException(status_code=400, detail="Nenhuma cena tem mídia para exportar.")
    patch_state(project_id, lambda s: s.update({"capcut": {"status": "building"}, "cancel_requested": False}))
    background_tasks.add_task(run_capcut_job, project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/capcut/download")
def download_capcut(project_id: str):
    state = read_state(project_id)
    cap = state.get("capcut", {})
    if cap.get("status") != "ready" or not cap.get("file"):
        raise HTTPException(status_code=409, detail="O projeto do CapCut ainda não está pronto.")
    path = project_dir(project_id) / cap["file"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Pacote do CapCut não encontrado no armazenamento.")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", state.get("title", "projeto"))[:50]
    return FileResponse(path, media_type="application/zip", filename=f"capcut_{safe}.zip")


@app.post("/api/projects/{project_id}/capcut-draft")
def generate_capcut_draft(project_id: str):
    """Gera um arquivo .js de rascunho do CapCut (Jianying) para importação direta."""
    state = read_state(project_id)
    if project_id in ACTIVE_JOBS or state.get("status") in ("rendering", "queued_render", "searching"):
        raise HTTPException(status_code=409, detail="Aguarde o robô terminar antes de exportar o draft.")
    if not any(s.get("options") for s in state.get("scenes", [])):
        raise HTTPException(status_code=400, detail="Nenhuma cena tem mídia para exportar.")
    try:
        result = capcut_draft.build_capcut_draft_js(project_id)
        return {"ok": True, "file": result["name"], "size_bytes": result["size_bytes"],
                "draft_name": result["draft_name"], "duration_us": result["duration_us"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não consegui gerar o draft: {str(exc)[:200]}")


@app.get("/api/projects/{project_id}/capcut-draft/download")
def download_capcut_draft(project_id: str):
    """Baixa o arquivo .js do draft do CapCut."""
    state = read_state(project_id)
    files = sorted(DRAFTS_DIR.glob("*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="Nenhum draft do CapCut encontrado. Gere primeiro.")
    path = files[0]
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", state.get("title", "projeto"))[:50]
    return FileResponse(path, media_type="application/javascript", filename=f"capcut_draft_{safe}.js")


@app.get("/api/projects/{project_id}/download")
def download_final(project_id: str):
    state = read_state(project_id)
    output_name = state.get("output_file")
    if state.get("status") != "complete" or not output_name:
        raise HTTPException(status_code=409, detail="O vídeo ainda não está pronto.")
    path = project_dir(project_id) / output_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo final não encontrado no armazenamento.")
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", state.get("title", "video"))[:50]
    return FileResponse(path, media_type="video/mp4", filename=f"{safe_title}.mp4")


@app.get("/api/projects/{project_id}/video")
def stream_final(project_id: str):
    """Mesmo arquivo do download, mas para tocar no player da página."""
    state = read_state(project_id)
    path = project_dir(project_id) / (state.get("output_file") or "video_final.mp4")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Vídeo ainda não gerado.")
    return FileResponse(path, media_type="video/mp4")


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if project_id in ACTIVE_JOBS:
        raise HTTPException(status_code=409, detail="Cancele o que está em andamento antes de apagar.")
    shutil.rmtree(project_dir(project_id), ignore_errors=True)
    return {"ok": True}
