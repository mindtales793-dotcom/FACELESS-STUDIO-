"""Exporta o projeto para um arquivo de rascunho do CapCut no formato .js (Jianying).

O arquivo .js pode ser importado direto no CapCut mobile (iOS/Android) ou desktop,
trazendo as cenas, narração, música, legendas e transições já montadas na timeline.

Formato baseado na estrutura draft_content.json do CapCut, serializada como módulo JS:
    module.exports = { ...draft... }
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from store import DATA_DIR, project_dir, read_state

DRAFTS_DIR = DATA_DIR / "capcut_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def _id() -> str:
    return str(uuid.uuid4()).upper()


def _us(seconds: float) -> int:
    return int(round(seconds * 1_000_000))


def _rgb(hex_color: str) -> list[float]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:40] or "draft"


def _base_draft(name: str, width: int, height: int) -> dict[str, Any]:
    now_us = int(time.time() * 1_000_000)
    return {
        "id": _id(),
        "draft_id": _id(),
        "draft_name": name,
        "draft_type": "video",
        "duration": 0,
        "fps": 30,
        "width": width,
        "height": height,
        "canvas": {"width": width, "height": height, "ratio": "16:9", "color": "#000000"},
        "materials": {
            "videos": [], "images": [], "audios": [], "texts": [], "effects": [],
            "stickers": [], "transitions": [], "canvases": [], "audio_effects": [],
            "audio_fades": [], "beats": [], "material_animations": [], "placeholders": [],
            "placeholder_infos": [], "speeds": [], "common_mask": [], "chromas": [],
            "text_templates": [], "realtime_denoises": [], "audio_pannings": [],
            "audio_pitch_shifts": [], "video_trackings": [], "hsl": [], "drafts": [],
            "color_curves": [], "hsl_curves": [], "primary_color_wheels": [],
            "log_color_wheels": [], "video_effects": [], "audio_balances": [],
            "handwrites": [], "manual_deformations": [], "manual_beautys": [],
            "plugin_effects": [], "sound_channel_mappings": [], "green_screens": [],
            "shapes": [], "material_colors": [], "digital_humans": [],
            "digital_human_model_dressing": [], "smart_crops": [], "ai_translates": [],
            "audio_track_indexes": [], "loudnesses": [], "vocal_beautifys": [],
            "vocal_separations": [], "smart_relights": [], "time_marks": [],
            "multi_language_refs": [], "video_shadows": [], "video_strokes": [],
            "video_radius": [],
        },
        "tracks": [],
        "selections": [],
        "composition": [],
        "version": "16.4.0",
        "app_version": "16.4.0",
        "create_time": now_us,
        "modify_time": now_us,
    }


def _material_video(path: Path, name: str, dur_us: int, width: int, height: int,
                    src_start_us: int = 0) -> dict[str, Any]:
    return {
        "id": _id(),
        "material_id": _id(),
        "path": str(path),
        "local_material_path": str(path),
        "file_path": str(path),
        "duration": dur_us,
        "trim_duration": dur_us,
        "src_duration": dur_us,
        "start": src_start_us,
        "width": width,
        "height": height,
        "type": "video",
        "import_type": "local",
        "is_from_quick_export": False,
        "resource_id": "",
        "cover_path": str(path),
        "audition_config": {},
        "added_time": int(time.time() * 1_000_000),
        "is_draft_cover": False,
        "material_render_type": 0,
        "clip_settings": {"is_hdr": False, "hdr_glow": 0, "is_dolby_vision": False},
        "extra_info": {},
        "is_ai_cover": False,
        "value": "",
    }


def _material_image(path: Path, name: str, dur_us: int, width: int, height: int) -> dict[str, Any]:
    return {
        "id": _id(),
        "material_id": _id(),
        "path": str(path),
        "local_material_path": str(path),
        "file_path": str(path),
        "duration": dur_us,
        "trim_duration": dur_us,
        "src_duration": dur_us,
        "start": 0,
        "width": width,
        "height": height,
        "type": "image",
        "import_type": "local",
        "is_from_quick_export": False,
        "resource_id": "",
        "cover_path": str(path),
        "audition_config": {},
        "added_time": int(time.time() * 1_000_000),
        "is_draft_cover": False,
        "material_render_type": 0,
        "clip_settings": {"is_hdr": False, "hdr_glow": 0, "is_dolby_vision": False},
        "extra_info": {},
        "is_ai_cover": False,
        "value": "",
    }


def _material_audio(path: Path, name: str, dur_us: int, vol: float = 1.0) -> dict[str, Any]:
    return {
        "id": _id(),
        "material_id": _id(),
        "path": str(path),
        "local_material_path": str(path),
        "file_path": str(path),
        "duration": dur_us,
        "trim_duration": dur_us,
        "src_duration": dur_us,
        "start": 0,
        "type": "audio",
        "import_type": "local",
        "resource_id": "",
        "resource_type": "",
        "import_time": int(time.time() * 1_000_000),
        "cover_path": "",
        "file_type": path.suffix.lower().lstrip("."),
        "audition_config": {},
        "added_time": int(time.time() * 1_000_000),
        "material_render_type": 0,
        "clip_settings": {"is_hdr": False, "hdr_glow": 0, "is_dolby_vision": False},
        "extra_info": {"volume": vol},
        "value": "",
    }


def _material_text(text: str, dur_us: int, font_size: float = 30.0,
                   color: str = "#FFFFFF", font: str = "Poppins") -> dict[str, Any]:
    return {
        "id": _id(),
        "material_id": _id(),
        "content": text,
        "font": font,
        "font_size": font_size,
        "color": color,
        "duration": dur_us,
        "trim_duration": dur_us,
        "start": 0,
        "type": "text",
        "import_type": "local",
        "resource_id": "",
        "added_time": int(time.time() * 1_000_000),
        "material_render_type": 0,
        "extra_info": {},
        "value": "",
    }


def _segment(material_id: str, track_id: str, start_us: int, dur_us: int,
             render_index: int, *, src_start_us: int = 0, volume: float = 1.0,
             refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": _id(),
        "material_id": material_id,
        "track_id": track_id,
        "start": start_us,
        "start_in_smart_motion_frame": 0,
        "duration": dur_us,
        "render_index": render_index,
        "clip": {
            "src_start": src_start_us,
            "duration": dur_us,
            "volume": volume,
            "speed": 1.0,
            "speed_curve": {},
            "transform": {
                "x": 0, "y": 0, "w": 100.0, "h": 100.0,
                "scalex": 100.0, "scaley": 100.0,
                "scalex_ref": 100.0, "scaley_ref": 100.0,
                "rotation": 0.0, "flip": 0,
                "anchor": {"x": 0.5, "y": 0.5},
                "mask_round_radius": 0.0,
                "mask_round_type": 0,
            },
            "alpha": 1.0,
            "style": {"fill_color": "#000000", "fill_enabled": False, "border_width": 0.0},
            "animation": [],
        },
        "keyframes": [],
        "refs": refs or [],
    }


def _track(kind: str, name: str, track_id: str) -> dict[str, Any]:
    return {
        "id": track_id,
        "type": kind,
        "name": name,
        "attribute": 0,
        "extra_info": {"is_expanded": True, "is_fold": False, "is_lock": False},
        "clips": [],
        "segments": [],
        "volume": 1.0,
        "mute": False,
        "locked": False,
        "render_index": 0,
    }


def build_capcut_draft_js(pid: str) -> dict[str, Any]:
    """Gera o arquivo .js do draft do CapCut e devolve {path, name, size_bytes}."""
    state = read_state(pid)
    folder = project_dir(pid)
    settings = state.get("settings", {})
    style = settings.get("style", {})
    ratio = settings.get("ratio", "16:9")

    if ratio == "16:9":
        w, h = 1920, 1080
    elif ratio == "9:16":
        w, h = 1080, 1920
    else:
        w, h = 1080, 1080

    title = state.get("title", "projeto")
    draft_name = f"{_slug(title)}_{time.strftime('%d%m_%H%M')}"
    draft = _base_draft(draft_name, w, h)
    mats = draft["materials"]

    scenes = sorted(state.get("scenes", []), key=lambda s: s.get("start", 0))
    audio_file = state.get("audio_file")
    srt_file = state.get("srt_file")
    srt_path = folder / srt_file if srt_file else None

    audio_len = 0.0
    if audio_file:
        try:
            from store import media_duration
            audio_len = media_duration(folder / audio_file)
        except Exception:
            audio_len = 0.0

    draft["duration"] = _us(audio_len)

    # --- vídeos/imagens das cenas ---
    video_track = _track("video", "Vídeos", _id())
    text_track = _track("text", "Legendas", _id())
    current_us = 0

    for idx, scene in enumerate(scenes):
        start = scene.get("start", 0)
        nxt = scenes[idx + 1]["start"] if idx + 1 < len(scenes) else audio_len
        dur = max(0.0, nxt - start)
        dur_us = _us(dur)

        mid = scene.get("id", f"scene_{idx}")
        opts = scene.get("options") or []
        sel = scene.get("selected", 0)
        opt = opts[sel] if opts and 0 <= sel < len(opts) else {}
        media_type = (opt or {}).get("media_type", "image")
        local_file = (opt or {}).get("local_file") or (opt or {}).get("path")

        if local_file:
            p = Path(local_file)
            if not p.exists():
                p = folder / local_file
        else:
            p = None

        if p and p.exists():
            if media_type == "video":
                mat = _material_video(p, opt.get("name", "vídeo"), dur_us,
                                      opt.get("width", w), opt.get("height", h),
                                      src_start_us=_us(start))
                mats["videos"].append(mat)
            else:
                mat = _material_image(p, opt.get("name", "imagem"), dur_us,
                                      opt.get("width", w), opt.get("height", h))
                mats["images"].append(mat)
            mat_id = mat["id"]
        else:
            # placeholder preto
            mat = {
                "id": _id(), "material_id": _id(), "type": "color",
                "color": "#18202d", "duration": dur_us,
                "width": w, "height": h,
            }
            mats["images"].append(mat)
            mat_id = mat["id"]

        seg = _segment(mat_id, video_track["id"], current_us, dur_us,
                       render_index=idx + 1, src_start_us=_us(start))
        video_track["segments"].append(seg)
        current_us += dur_us

    draft["tracks"].append(video_track)

    # --- legendas do SRT ---
    if srt_path and srt_path.exists():
        from scenes import parse_srt
        try:
            cues = parse_srt(srt_path.read_text(encoding="utf-8-sig", errors="replace"))
            sub_track = _track("text", "Legendas (SRT)", _id())
            for i, cue in enumerate(cues):
                txt = str(cue.get("text", ""))
                dur = max(0.1, float(cue.get("end", 0)) - float(cue.get("start", 0)))
                mat = _material_text(txt, _us(dur), font_size=28.0,
                                     color=style.get("subtitles", {}).get("color", "#FFFFFF"))
                mats["texts"].append(mat)
                seg = _segment(mat["id"], sub_track["id"], _us(float(cue.get("start", 0))),
                               _us(dur), render_index=100 + i)
                sub_track["segments"].append(seg)
            draft["tracks"].append(sub_track)
        except Exception:
            pass

    # --- CTA (sticker de inscrição) ---
    cta = style.get("cta", {})
    if cta.get("enabled"):
        cta_text = cta.get("text") or "SE INSCREVA NO CANAL"
        cta_dur = max(1.0, float(cta.get("seconds", 5.0)))
        cta_start = max(0.0, audio_len - cta_dur - 0.5)
        mat = _material_text(cta_text, _us(cta_dur), font_size=34.0,
                             color=style.get("cta", {}).get("style", {}).get("text", "#FFFFFF") if isinstance(style.get("cta", {}).get("style"), dict) else "#FFFFFF")
        mats["texts"].append(mat)
        cta_track = _track("text", "Inscrição", _id())
        seg = _segment(mat["id"], cta_track["id"], _us(cta_start), _us(cta_dur),
                       render_index=200)
        cta_track["segments"].append(seg)
        draft["tracks"].append(cta_track)

    # --- narração ---
    narr_track = _track("audio", "Narração", _id())
    if audio_file:
        p = folder / audio_file
        if p.exists():
            mat = _material_audio(p, audio_file, _us(audio_len),
                                  float(settings.get("audio", {}).get("narration_volume", 1.0)))
            mats["audios"].append(mat)
            seg = _segment(mat["id"], narr_track["id"], 0, _us(audio_len),
                           render_index=1, volume=float(settings.get("audio", {}).get("narration_volume", 1.0)))
            narr_track["segments"].append(seg)
    draft["tracks"].append(narr_track)

    # --- música ---
    music_id = settings.get("audio", {}).get("music_id")
    music_vol = float(settings.get("audio", {}).get("music_volume", 0.14))
    if music_id:
        from store import MUSIC_DIR
        p = MUSIC_DIR / f"{music_id}.mp3"
        if not p.exists():
            # tenta encontrar qualquer extensão
            for ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg"):
                cand = MUSIC_DIR / f"{music_id}{ext}"
                if cand.exists():
                    p = cand
                    break
        if p.exists():
            from store import media_duration
            try:
                mus_dur = media_duration(p)
            except Exception:
                mus_dur = audio_len
            mat = _material_audio(p, p.name, _us(mus_dur), music_vol)
            mats["audios"].append(mat)
            mus_track = _track("audio", "Música", _id())
            # loop da música até o fim do áudio
            t = 0.0
            idx = 0
            while t < audio_len:
                seg_dur = min(mus_dur - 0.1, audio_len - t)
                if seg_dur <= 0:
                    break
                seg = _segment(mat["id"], mus_track["id"], _us(t), _us(seg_dur),
                               render_index=110 + idx, volume=music_vol)
                mus_track["segments"].append(seg)
                t += seg_dur
                idx += 1
            draft["tracks"].append(mus_track)

    # --- meta info ---
    meta = {
        "draft_id": draft["draft_id"],
        "draft_name": draft_name,
        "draft_type": "video",
        "duration": draft["duration"],
        "fps": 30,
        "width": w,
        "height": h,
        "create_time": draft["create_time"],
        "modify_time": draft["modify_time"],
        "draft_cover": "",
        "draft_cover_path": "",
        "draft_path": "",
        "draft_json_file": "",
        "draft_root_path": "",
        "draft_fold_path": "",
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "is_ae_produce": False,
        "is_ai_packaging_used": False,
        "is_ai_shorts": False,
        "is_ai_translate": False,
        "is_article_video_draft": False,
        "is_cloud_temp_draft": False,
        "is_from_deeplink": "false",
        "is_invisible": False,
        "is_web_article_video": False,
        "new_version": "164.0.0",
        "removable_storage_device": "",
        "segment_extra_info": [],
        "timeline_materials_size": 0,
        "web_article_video_enter_from": "",
    }

    # escreve o arquivo .js (módulo Node.js / CommonJS)
    out_name = f"{draft_name}.js"
    out_path = DRAFTS_DIR / out_name
    content = (
        "// Faceless Cloud Studio - Draft do CapCut (Jianying)\n"
        "// Importe este arquivo no CapCut mobile ou desktop.\n"
        "module.exports = " + json.dumps({"draft": draft, "meta": meta}, ensure_ascii=False, indent=2) + ";\n"
    )
    out_path.write_text(content, encoding="utf-8")

    return {
        "path": str(out_path),
        "name": out_name,
        "size_bytes": out_path.stat().st_size,
        "draft_name": draft_name,
        "duration_us": draft["duration"],
    }
