"""Exporta o projeto para um rascunho do CapCut (desktop 8.x) em um .zip.

O zip traz a pasta do rascunho (draft_content.json, draft_meta_info.json e Resources/ com toda a mídia)
mais um instalador que copia a pasta para a lista de rascunhos do CapCut. Os caminhos usam o token
portátil do CapCut, então a mídia continua encontrada se o rascunho for renomeado ou duplicado.

O que vai para o CapCut: cenas na ordem e duração do vídeo, zoom lento nas fotos (keyframes), trilha da
narração, trilha da música (com o volume escolhido) e legendas como texto. Cor do template, transições,
vinheta e ducking ficam só no MP4 renderizado, porque dependem de efeitos da biblioteca do CapCut.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

import styles
from scenes import parse_srt
from store import Tracker, ffmpeg_path, media_duration, now_iso, patch_state, probe_media, project_dir, read_state

TOKEN = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"
PHOTO_DURATION = 10_800_000_000  # 3 h, como o CapCut grava para fotos


def _id() -> str:
    return str(uuid.uuid4()).upper()


def _us(seconds: float) -> int:
    return int(round(seconds * 1_000_000))


def _rgb(hex_color: str) -> list[float]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _is_light(hex_color: str) -> bool:
    r, g, b = _rgb(hex_color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 0.6


def _base_draft(name: str, width: int, height: int, ratio: str) -> dict[str, Any]:
    keys = ["flowers", "videos", "tail_leaders", "audios", "images", "texts", "effects", "stickers", "canvases", "transitions",
            "audio_effects", "audio_fades", "beats", "material_animations", "placeholders", "placeholder_infos", "speeds",
            "common_mask", "chromas", "text_templates", "realtime_denoises", "audio_pannings", "audio_pitch_shifts",
            "video_trackings", "hsl", "drafts", "color_curves", "hsl_curves", "primary_color_wheels", "log_color_wheels",
            "video_effects", "audio_balances", "handwrites", "manual_deformations", "manual_beautys", "plugin_effects",
            "sound_channel_mappings", "green_screens", "shapes", "material_colors", "digital_humans",
            "digital_human_model_dressing", "smart_crops", "ai_translates", "audio_track_indexes", "loudnesses",
            "vocal_beautifys", "vocal_separations", "smart_relights", "time_marks", "multi_language_refs",
            "video_shadows", "video_strokes", "video_radius"]
    platform = {"os": "windows", "os_version": "10.0.26200", "app_id": 359289, "app_version": "8.5.0", "app_source": "cc",
                "device_id": "", "hard_disk_id": "", "mac_address": ""}
    now = int(time.time())
    return {
        "id": _id(), "version": 360000, "new_version": "167.0.0", "name": name, "duration": 0,
        "create_time": now, "update_time": now, "fps": 30.0, "is_drop_frame_timecode": False, "color_space": -1,
        "config": {
            "video_mute": False, "record_audio_last_index": 1, "extract_audio_last_index": 1, "original_sound_last_index": 1,
            "subtitle_recognition_id": "", "subtitle_taskinfo": [], "lyrics_recognition_id": "", "lyrics_taskinfo": [],
            "subtitle_sync": True, "lyrics_sync": True, "voice_change_sync": False, "sticker_max_index": 1,
            "adjust_max_index": 1, "material_save_mode": 0, "export_range": None, "maintrack_adsorb": True,
            "combination_max_index": 1, "attachment_info": [], "zoom_info_params": None, "system_font_list": [],
            "multi_language_mode": "none", "multi_language_main": "none", "multi_language_current": "none",
            "multi_language_list": [], "subtitle_keywords_config": None, "use_float_render": False,
        },
        "canvas_config": {"ratio": ratio if ratio in ("16:9", "9:16", "1:1") else "original", "width": width, "height": height, "background": None},
        "tracks": [], "group_container": None,
        "materials": {k: [] for k in keys},
        "keyframes": {k: [] for k in ("videos", "audios", "texts", "stickers", "filters", "adjusts", "handwrites", "effects")},
        "keyframe_graph_list": [], "platform": platform, "last_modified_platform": platform, "mutable_config": None,
        "cover": None, "retouch_cover": None, "extra_info": None, "relationships": [],
        "render_index_track_mode_on": True, "free_render_index_mode_on": False, "static_cover_image_path": "",
        "source": "default", "time_marks": None, "path": "", "lyrics_effects": [],
        "uneven_animation_template_info": {"composition": "", "content": "", "order": "", "sub_template_info_list": []},
        "draft_type": "video", "smart_ads_info": {"page_from": "", "routine": "", "draft_url": ""},
        "function_assistant_info": {
            "smart_rec_applied": False, "fixed_rec_applied": False, "auto_adjust": False, "auto_adjust_segid_list": [],
            "color_correction": False, "color_correction_segid_list": [], "enhance_quality": False, "smooth_slow_motion": False,
            "deflicker_segid_list": [], "video_noise_segid_list": [], "enhance_quality_segid_list": [], "smart_segid_list": [],
            "retouch": False, "retouch_segid_list": [], "enhande_voice": False, "enhance_voice_segid_list": [],
            "audio_noise_segid_list": [], "auto_caption": False, "auto_caption_segid_list": [], "auto_caption_template_id": "",
            "caption_opt": False, "caption_opt_segid_list": [], "eye_correction": False, "eye_correction_segid_list": [],
            "normalize_loudness": False, "normalize_loudness_segid_list": [], "normalize_loudness_audio_denoise_segid_list": [],
            "auto_adjust_fixed": False, "auto_adjust_fixed_value": 50.0, "color_correction_fixed": False,
            "color_correction_fixed_value": 50.0, "normalize_loudness_fixed": False, "enhande_voice_fixed": False,
            "retouch_fixed": False, "enhance_quality_fixed": False, "smooth_slow_motion_fixed": False, "fps": {"num": 0, "den": 1},
        },
    }


def _companions(draft: dict[str, Any], track_type: str) -> list[str]:
    mats = draft["materials"]
    ids: list[str] = []

    def add(kind: str, data: dict[str, Any]) -> None:
        data["id"] = _id()
        mats.setdefault(kind, []).append(data)
        ids.append(data["id"])

    add("speeds", {"type": "speed", "speed": 1, "mode": 0, "curve_speed": None})
    add("placeholder_infos", {"type": "placeholder_info", "error_path": "", "error_text": "", "meta_type": "none", "res_path": "", "res_text": ""})
    add("sound_channel_mappings", {"type": "none", "audio_channel_mapping": 0, "is_config_open": False})
    add("vocal_separations", {"type": "vocal_separation", "choice": 0, "enter_from": "", "final_algorithm": "", "production_path": "", "removed_sounds": [], "time_range": None})
    if track_type == "video":
        add("canvases", {"type": "canvas_color", "album_image": "", "blur": 0, "color": "", "image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        add("material_colors", {"type": "material_color", "gradient_angle": 90, "gradient_colors": [], "gradient_percents": [], "height": 0, "is_color_clip": False, "is_gradient": False, "solid_color": "", "width": 0})
    return ids


def _segment(material_id: str, track_id: str, start_us: int, dur_us: int, refs: list[str], render_index: int, *, src_start: int = 0, volume: float = 1.0) -> dict[str, Any]:
    return {
        "id": _id(), "material_id": material_id, "raw_segment_id": track_id,
        "target_timerange": {"start": start_us, "duration": dur_us},
        "source_timerange": {"start": src_start, "duration": dur_us},
        "speed": 1, "volume": volume, "visible": True, "reverse": False,
        "clip": {"alpha": 1, "rotation": 0, "scale": {"x": 1, "y": 1}, "transform": {"x": 0, "y": 0}, "flip": {"horizontal": False, "vertical": False}},
        "render_index": render_index, "track_render_index": 0, "track_attribute": 0,
        "extra_material_refs": refs, "common_keyframes": [], "keyframe_refs": [],
    }


def _track(kind: str, name: str) -> dict[str, Any]:
    return {"id": _id(), "type": kind, "name": name, "attribute": 0, "segments": [], "is_default_name": False, "flag": 0}


def _scale_keyframes(seg: dict[str, Any], dur_us: int, v0: float, v1: float) -> None:
    def kf(offset: int, value: float) -> dict[str, Any]:
        return {"id": _id(), "curveType": "FreeCurveInOut", "time_offset": offset, "left_control": {"x": 0, "y": 0},
                "right_control": {"x": 0, "y": 0}, "values": [value], "string_value": "", "graphID": ""}
    for prop in ("KFTypeScaleX", "KFTypeScaleY"):
        seg["common_keyframes"].append({"id": _id(), "material_id": "", "property_type": prop, "keyframe_list": [kf(0, v0), kf(dur_us, v1)]})


def _text_content(text: str, size: float, color: list[float], bold: bool, stroke: list[float] | None) -> str:
    style: dict[str, Any] = {
        "range": [0, len(text.encode("utf-16-le")) // 2], "size": size, "bold": bold, "italic": False, "underline": False,
        "fill": {"alpha": 1, "content": {"render_type": "solid", "solid": {"alpha": 1, "color": color}}},
        "strokes": [{"content": {"solid": {"alpha": 1, "color": stroke}}, "width": 0.08}] if stroke else [],
    }
    return json.dumps({"styles": [style], "text": text}, ensure_ascii=False)


def _slug(text: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())[:40].strip("_")
    return clean or "projeto"


def build_capcut_package(pid: str, T: Tracker) -> Path:
    from render import ensure_media, music_path  # evita import circular

    state = read_state(pid)
    folder = project_dir(pid)
    settings = state.get("settings", {})
    style = styles.resolve_style(settings.get("template"), settings.get("style"))
    ratio = settings.get("ratio", "16:9")
    width, height = styles.ratio_dimensions(ratio, settings.get("quality", "720p"))
    audio_opts = settings.get("audio", {})
    portrait = height > width

    T.update(stage="capcut", status="running", detail="Preparando mídia", progress=5, log="Montando o projeto do CapCut...")
    patch_state(pid, lambda s: s.update({"capcut": {"status": "building", "file": None, "updated_at": now_iso()}}))
    media = ensure_media(pid, T, None, None)
    T.check()

    audio_path = folder / state["audio_file"]
    audio_len = media_duration(audio_path)
    scenes = sorted(state.get("scenes", []), key=lambda s: s["start"])
    for i, scene in enumerate(scenes):
        start = 0.0 if i == 0 else float(scene["start"])
        nxt = float(scenes[i + 1]["start"]) if i + 1 < len(scenes) else audio_len
        scene["render_start"] = max(0.0, start)
        scene["render_end"] = min(audio_len, max(scene["render_start"] + 0.25, nxt))

    title = state.get("title", "Projeto")
    draft_name = f"{_slug(title)}_{time.strftime('%d%m_%H%M')}"
    draft = _base_draft(draft_name, width, height, ratio)
    draft["duration"] = _us(audio_len)
    mats = draft["materials"]
    resources: dict[str, Path] = {}  # arcname dentro de Resources -> arquivo de origem

    def register(path: Path) -> tuple[str, str]:
        """Devolve (id_do_material, caminho portátil) para um arquivo, copiando uma vez."""
        key = str(path)
        for arc, src in resources.items():
            if str(src) == key:
                mid = arc.rsplit(".", 1)[0]
                return mid, f"{TOKEN}\\Resources\\{arc}"
        mid = _id()
        arc = f"{mid}{path.suffix.lower()}"
        resources[arc] = path
        return mid, f"{TOKEN}\\Resources\\{arc}"

    # ---- trilha de vídeo
    T.update(stage="capcut", detail="Montando a trilha de vídeo", progress=30)
    video_track = _track("video", "video")
    material_by_file: dict[str, str] = {}
    cover_source: Path | None = None
    for n, scene in enumerate(scenes):
        info = media.get(scene["id"])
        start_us, dur_us = _us(scene["render_start"]), _us(scene["render_end"]) - _us(scene["render_start"])
        if not info:
            continue
        path: Path = info["path"]
        cover_source = cover_source or path
        mw, mh = int(info["info"]["width"] or width), int(info["info"]["height"] or height)
        is_photo = info["media_type"] == "image" or info["info"]["duration"] <= 0.1
        key = str(path)
        if key not in material_by_file:
            mid, local = register(path)
            ext = path.suffix.lower()
            material = {
                "id": mid, "path": local, "material_name": f"cena_{n + 1:03d}{ext}", "type": "photo" if is_photo else "video",
                "duration": PHOTO_DURATION if is_photo else _us(info["info"]["duration"]), "width": mw, "height": mh,
                "category_id": "", "category_name": "local", "check_flag": 7,
                "crop": {"lower_left_x": 0, "lower_left_y": 1, "lower_right_x": 1, "lower_right_y": 1, "upper_left_x": 0, "upper_left_y": 0, "upper_right_x": 1, "upper_right_y": 0},
                "has_audio": not is_photo, "extra_type_option": 0, "formula_id": "", "freeze": None, "intensifies_audio_path": "",
                "intensifies_path": "", "is_ai_generate_content": False, "is_copyright": False, "is_text_edit_overdub": False,
                "is_unified_beauty_mode": False, "local_id": "", "local_material_id": "", "material_url": "", "media_path": "",
                "object_locked": None, "origin_material_id": "", "request_id": "", "reverse_path": "", "source_platform": 0,
                "stable": {"matrix_path": "", "stable_level": 0, "time_range": {"duration": 0, "start": 0}}, "team_id": "",
                "video_algorithm": {"algorithms": [], "deflicker": None, "motion_blur_config": None, "noise_reduction": None, "path": "", "quality_enhance": None, "time_range": None},
            }
            mats["videos"].append(material)
            material_by_file[key] = mid
        mid = material_by_file[key]
        contain = min(width / mw, height / mh)
        cover = max(width / mw, height / mh) / contain  # faz a mídia preencher o quadro, como o MP4
        motion = style.get("motion", "none")
        if motion == "alternate":
            motion = "zoom_in" if n % 2 == 0 else "zoom_out"
        strength = float(style.get("motion_strength", 0.1))
        if is_photo:
            pieces = [(start_us, dur_us, 0)]
        else:  # clipe mais curto que a cena: repete em sequência, como o render faz com o loop
            src_us = max(500_000, _us(info["info"]["duration"]))
            pieces, t, remaining = [], start_us, dur_us
            while remaining > 0:
                d = min(src_us, remaining)
                pieces.append((t, d, 0))
                t += d
                remaining -= d
        for p_start, p_dur, p_src in pieces:
            seg = _segment(mid, video_track["id"], p_start, p_dur, _companions(draft, "video"), 14000, src_start=p_src, volume=0.0)
            seg["clip"]["scale"] = {"x": cover, "y": cover}
            if is_photo and motion in ("zoom_in", "zoom_out"):
                a, b = (cover, cover * (1 + strength)) if motion == "zoom_in" else (cover * (1 + strength), cover)
                _scale_keyframes(seg, p_dur, a, b)
            video_track["segments"].append(seg)
    draft["tracks"].append(video_track)

    # ---- legendas
    sub = style["subtitles"]
    cues = parse_srt((folder / state["srt_file"]).read_text(encoding="utf-8-sig", errors="replace"))
    if sub.get("enabled", True):
        T.update(stage="capcut", detail="Adicionando as legendas", progress=55)
        text_track = _track("text", "legendas")
        size = round(float(sub["size"]) * 333 * (0.8 if portrait else 1.0), 1)
        y = {"bottom": -0.78, "lower_third": -0.55, "middle": 0.0, "top": 0.78}.get(sub.get("position", "bottom"), -0.78)
        stroke = _rgb(sub["outline_color"]) if float(sub.get("outline", 0)) > 0 and not sub.get("box") else None
        for cue in cues:
            text = " ".join(str(cue["text"]).split())
            if sub.get("uppercase"):
                text = text.upper()
            dur = _us(cue["end"]) - _us(cue["start"])
            if dur <= 0 or not text:
                continue
            mat_id = _id()
            mats["texts"].append({
                "id": mat_id, "type": "text", "content": _text_content(text, size, _rgb(sub["color"]), bool(sub.get("bold")), stroke),
                "alignment": 1, "font_size": size, "text_color": sub["color"], "typesetting": 0, "letter_spacing": 0,
                "line_spacing": 0.02, "line_feed": 1, "line_max_width": 0.82, "force_apply_line_max_width": False,
                "check_flag": 7 | (8 if stroke else 0), "fixed_width": -1, "fixed_height": -1,
            })
            seg = _segment(mat_id, text_track["id"], _us(cue["start"]), dur, _companions(draft, "text"), 15000)
            seg["clip"]["transform"] = {"x": 0, "y": y}
            text_track["segments"].append(seg)
        draft["tracks"].append(text_track)

    # ---- chamada de inscrição localizada (mesmo texto do MP4, como texto editável)
    plan = styles.cta_plan(style, audio_len, cues)
    if plan:
        T.update(stage="capcut", detail="Adicionando a chamada de inscrição", progress=62)
        palette = plan["palette"]
        start_us = _us(plan["start"])
        dur_us = max(1, _us(plan["end"]) - start_us)
        main_hex, sub_hex = str(palette["text"]), str(palette.get("sub") or palette["text"])
        stroke_main = _rgb("#000000" if _is_light(main_hex) else "#FFFFFF")
        stroke_sub = _rgb("#000000" if _is_light(sub_hex) else "#FFFFFF")
        main_size = round(0.042 * 333 * (0.82 if portrait else 1.0), 1)
        sub_size = round(0.023 * 333 * (0.82 if portrait else 1.0), 1)
        main_y = 0.66 if plan["anchor"] == "top" else -0.60
        sub_y = main_y - 0.12 if plan["anchor"] == "top" else main_y - 0.14

        cta_track = _track("text", "inscrição")
        main_id = _id()
        mats["texts"].append({
            "id": main_id, "type": "text",
            "content": _text_content(str(plan["main"]).upper(), main_size, _rgb(main_hex), True, stroke_main),
            "alignment": 1, "font_size": main_size, "text_color": main_hex, "typesetting": 0, "letter_spacing": 0,
            "line_spacing": 0.02, "line_feed": 1, "line_max_width": 0.9, "force_apply_line_max_width": False,
            "check_flag": 7 | 8, "fixed_width": -1, "fixed_height": -1,
        })
        seg = _segment(main_id, cta_track["id"], start_us, dur_us, _companions(draft, "text"), 16000)
        seg["clip"]["transform"] = {"x": 0, "y": main_y}
        cta_track["segments"].append(seg)
        draft["tracks"].append(cta_track)

        if str(plan.get("sub") or "").strip():
            sub_track = _track("text", "inscrição apoio")
            sub_id = _id()
            mats["texts"].append({
                "id": sub_id, "type": "text",
                "content": _text_content(str(plan["sub"]), sub_size, _rgb(sub_hex), False, stroke_sub),
                "alignment": 1, "font_size": sub_size, "text_color": sub_hex, "typesetting": 0, "letter_spacing": 0,
                "line_spacing": 0.02, "line_feed": 1, "line_max_width": 0.9, "force_apply_line_max_width": False,
                "check_flag": 7 | 8, "fixed_width": -1, "fixed_height": -1,
            })
            seg = _segment(sub_id, sub_track["id"], start_us, dur_us, _companions(draft, "text"), 16000)
            seg["clip"]["transform"] = {"x": 0, "y": sub_y}
            sub_track["segments"].append(seg)
            draft["tracks"].append(sub_track)

    # ---- áudio
    T.update(stage="capcut", detail="Adicionando narração e música", progress=70)

    def audio_material(path: Path, name: str, dur_us: int) -> str:
        mid, local = register(path)
        mats["audios"].append({
            "id": mid, "path": local, "name": name, "duration": dur_us, "type": "extract_music", "category_id": "",
            "category_name": "local", "check_flag": 1, "music_id": "", "request_id": "", "source_platform": 0, "team_id": "",
            "text_id": "", "tone_category_id": "", "tone_category_name": "", "tone_effect_id": "", "tone_effect_name": "",
            "tone_platform": "", "tone_second_category_id": "", "tone_second_category_name": "", "tone_speaker": "",
            "tone_type": "", "wave_points": [],
        })
        return mid

    narr_track = _track("audio", "narracao")
    narr_id = audio_material(audio_path, "narracao" + audio_path.suffix.lower(), _us(audio_len))
    narr_track["segments"].append(_segment(narr_id, narr_track["id"], 0, _us(audio_len), _companions(draft, "audio"), 11000, volume=float(audio_opts.get("narration_volume", 1.0))))
    draft["tracks"].append(narr_track)

    music = music_path(audio_opts)
    if music:
        mdur = media_duration(music)
        music_track = _track("audio", "musica")
        music_id = audio_material(music, "musica" + music.suffix.lower(), _us(mdur))
        t, remaining = 0, _us(audio_len)
        while remaining > 0:
            d = min(_us(mdur), remaining)
            music_track["segments"].append(_segment(music_id, music_track["id"], t, d, _companions(draft, "audio"), 11000, volume=float(audio_opts.get("music_volume", 0.14))))
            t += d
            remaining -= d
            if not audio_opts.get("loop", True):
                break
        draft["tracks"].append(music_track)

    # ---- capa
    T.update(stage="capcut", detail="Gravando arquivos", progress=82)
    cover_bytes: bytes | None = None
    if cover_source:
        tmp = folder / "capcut_cover.jpg"
        try:
            subprocess.run([ffmpeg_path(), "-y", "-i", str(cover_source), "-vf", "scale=640:-2", "-frames:v", "1", str(tmp)], capture_output=True, timeout=60, check=True)
            cover_bytes = tmp.read_bytes()
        except Exception:
            cover_bytes = None
        tmp.unlink(missing_ok=True)

    now_us = int(time.time() * 1_000_000)
    meta = {
        "cloud_draft_cover": False, "cloud_draft_sync": False, "cloud_package_completed_time": "", "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False, "draft_cloud_package_type": "", "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "", "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg", "draft_deeplink_url": "",
        "draft_enterprise_info": {"draft_enterprise_extra": "", "draft_enterprise_id": "", "draft_enterprise_name": "", "enterprise_material": []},
        "draft_fold_path": "", "draft_id": draft["id"], "draft_is_ae_produce": False, "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False, "draft_is_ai_translate": False, "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False, "draft_is_from_deeplink": "false", "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_materials": [{"type": t, "value": []} for t in (0, 1, 2, 3, 6, 7, 8)],
        "draft_materials_copied_info": [], "draft_name": draft_name, "draft_need_rename_folder": False,
        "draft_new_version": "164.0.0", "draft_removable_storage_device": "", "draft_root_path": "",
        "draft_segment_extra_info": [], "draft_timeline_materials_size_": 0, "draft_type": "",
        "draft_web_article_video_enter_from": "", "tm_draft_cloud_completed": "", "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0, "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1, "tm_draft_create": now_us, "tm_draft_modified": now_us, "tm_draft_removed": 0,
        "tm_duration": _us(audio_len),
    }

    out_zip = folder / "capcut_projeto.zip"
    tmp_zip = folder / "capcut_projeto.zip.part"
    root_name = f"CapCut_{draft_name}"
    with zipfile.ZipFile(tmp_zip, "w") as z:
        def put_text(arc: str, text: str, compress: bool = True) -> None:
            z.writestr(zipfile.ZipInfo(arc, time.localtime()[:6]), text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED)

        base = f"{root_name}/{draft_name}"
        put_text(f"{base}/draft_content.json", json.dumps(draft, ensure_ascii=False, separators=(",", ":")))
        put_text(f"{base}/draft_meta_info.json", json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
        if cover_bytes:
            z.writestr(zipfile.ZipInfo(f"{base}/draft_cover.jpg", time.localtime()[:6]), cover_bytes, compress_type=zipfile.ZIP_STORED)
        total = max(1, len(resources))
        for i, (arc, src) in enumerate(resources.items()):
            T.check()
            z.write(src, f"{base}/Resources/{arc}", compress_type=zipfile.ZIP_STORED)
            T.update(stage="capcut", progress=82 + int(16 * (i + 1) / total), detail=f"Copiando mídia {i + 1} de {total}")
        z.write(folder / state["srt_file"], f"{root_name}/legendas.srt", compress_type=zipfile.ZIP_DEFLATED)
        put_text(f"{root_name}/install_capcut_draft.py", INSTALLER_PY)
        put_text(f"{root_name}/INSTALAR_NO_CAPCUT.bat", INSTALLER_BAT.replace("\n", "\r\n"))
        put_text(f"{root_name}/LEIA-ME.txt", README_TXT.format(name=draft_name).replace("\n", "\r\n"))
    tmp_zip.replace(out_zip)
    size_mb = out_zip.stat().st_size / 1024 / 1024
    patch_state(pid, lambda s: s.update({"capcut": {"status": "ready", "file": out_zip.name, "name": draft_name, "size_mb": round(size_mb, 1), "updated_at": now_iso()}}))
    T.update(stage="capcut", status="done", detail=f"Pacote de {size_mb:.0f} MB", progress=100, log=f"Projeto do CapCut pronto ({size_mb:.0f} MB).")
    return out_zip


INSTALLER_PY = r'''#!/usr/bin/env python3
"""Copia o rascunho para a pasta de projetos do CapCut e registra na lista de projetos."""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent


def default_root():
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    return home / ".local" / "share" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def capcut_running():
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
        return "capcut.exe" in out
    except Exception:
        return False


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else default_root()
    drafts = [p for p in HERE.iterdir() if p.is_dir() and (p / "draft_content.json").exists()]
    if not drafts:
        print("Nenhum rascunho encontrado ao lado deste script.")
        return 1
    if capcut_running():
        print("O CapCut está aberto. Feche o CapCut por completo e rode de novo.")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    root_meta_path = root / "root_meta_info.json"
    if root_meta_path.exists():
        shutil.copy2(root_meta_path, root / "root_meta_info.json.bak")
        root_meta = json.loads(root_meta_path.read_text(encoding="utf-8"))
    else:
        root_meta = {}
    root_meta.setdefault("all_draft_store", [])
    root_meta.setdefault("draft_ids", [])
    root_meta.setdefault("root_path", str(root))

    for src in drafts:
        name = src.name
        dest = root / name
        n = 2
        while dest.exists():
            name = f"{src.name}_{n}"
            dest = root / name
            n += 1
        shutil.copytree(src, dest)
        meta_file = dest / "draft_meta_info.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        now = int(time.time() * 1_000_000)
        draft_id = meta.get("draft_id") or str(uuid.uuid4()).upper()
        if any(e.get("draft_id") == draft_id for e in root_meta["all_draft_store"]):
            draft_id = str(uuid.uuid4()).upper()
        meta.update({"draft_name": name, "draft_fold_path": str(dest), "draft_root_path": str(root), "draft_id": draft_id, "tm_draft_modified": now})
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        entry = {
            "cloud_draft_cover": False, "cloud_draft_sync": False, "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "", "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "", "draft_cover": str(dest / "draft_cover.jpg"),
            "draft_fold_path": str(dest), "draft_id": draft_id, "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False, "draft_is_invisible": False, "draft_is_web_article_video": False,
            "draft_json_file": str(dest / "draft_content.json"), "draft_name": name,
            "draft_new_version": meta.get("draft_new_version", "164.0.0"), "draft_root_path": str(root),
            "draft_timeline_materials_size": 0, "draft_type": "", "draft_web_article_video_enter_from": "",
            "streaming_edit_draft_ready": True, "tm_draft_cloud_completed": "", "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0, "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1, "tm_draft_create": meta.get("tm_draft_create", now), "tm_draft_modified": now,
            "tm_draft_removed": 0, "tm_duration": meta.get("tm_duration", 0),
        }
        root_meta["all_draft_store"].insert(0, entry)
        root_meta["draft_ids"].append(draft_id)
        print("Rascunho instalado:", dest)

    root_meta_path.write_text(json.dumps(root_meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("\nPronto. Abra o CapCut: o projeto aparece no topo da lista de rascunhos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

INSTALLER_BAT = r'''@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo Feche o CapCut por completo antes de continuar.
pause
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 install_capcut_draft.py %*
  goto fim
)
where python >nul 2>nul
if %errorlevel%==0 (
  python install_capcut_draft.py %*
  goto fim
)
echo Python nao foi encontrado. Siga o passo a passo manual do LEIA-ME.txt.
:fim
echo.
pause
'''

README_TXT = '''Projeto do CapCut: {name}

COMO IMPORTAR (Windows)
1. Feche o CapCut por completo.
2. Extraia este zip em qualquer pasta.
3. Dê dois cliques em INSTALAR_NO_CAPCUT.bat (precisa de Python instalado).
4. Abra o CapCut. O projeto aparece no topo dos rascunhos.

SE O INSTALADOR NÃO FUNCIONAR (passo manual)
Copie a pasta "{name}" para:
  %LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft
Abra o CapCut. Se o projeto não aparecer na lista, rode o instalador.

O QUE VEM NO PROJETO
- Cenas na ordem e na duração do vídeo, com a mídia dentro da pasta Resources.
- Zoom lento nas fotos (keyframes de escala).
- Trilha da narração e trilha da música com o volume escolhido.
- Legendas como texto, com cor, tamanho e posição aproximados do template.

O QUE FICA SÓ NO MP4
Cor do template, vinheta, grão, transições e redução automática da música (ducking).
Aplique filtros e transições do próprio CapCut se quiser algo parecido.

OBSERVAÇÕES
- Feito para o CapCut desktop 8.x. Se a sua versão abrir o projeto vazio ou pedir para
  relinkar a mídia, avise: o formato do rascunho muda entre versões.
- O instalador faz cópia de segurança do root_meta_info.json antes de alterar.
'''
