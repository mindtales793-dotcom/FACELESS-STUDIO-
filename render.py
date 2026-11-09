"""Motor de render: baixa a mídia, aplica o estilo, mixa o áudio e exporta o MP4."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

import styles
import project_config
from scenes import parse_srt
from store import (
    MAX_MEDIA_MB, MUSIC_DIR, Cancelled, Tracker, ffmpeg_has_filter, ffmpeg_path, media_duration,
    patch_state, probe_media, project_dir, read_state, run_ffmpeg, default_stages, now_iso,
)

FPS = 24
DUCK = {"low": (0.06, 3), "medium": (0.035, 6), "high": (0.02, 12)}


# ------------------------------------------------------------------ download

def download_file(url: str, dest: Path) -> None:
    max_bytes = MAX_MEDIA_MB * 1024 * 1024
    last: Exception | None = None
    for attempt in range(2):
        try:
            with requests.get(url, stream=True, timeout=(20, 120), headers={"User-Agent": "FacelessCloudStudio/0.4"}) as response:
                response.raise_for_status()
                declared = int(response.headers.get("content-length") or 0)
                if declared and declared > max_bytes:
                    raise RuntimeError(f"Mídia acima do limite de {MAX_MEDIA_MB} MB. Escolha outra opção ou aumente MAX_MEDIA_MB.")
                written = 0
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            written += len(chunk)
                            if written > max_bytes:
                                raise RuntimeError(f"Mídia acima do limite de {MAX_MEDIA_MB} MB.")
                            handle.write(chunk)
                tmp.replace(dest)
                return
        except Exception as exc:
            last = exc
            dest.with_suffix(dest.suffix + ".part").unlink(missing_ok=True)
            if "limite" in str(exc):
                break
            time.sleep(1.5)
    raise RuntimeError(str(last))


def _ext_for(url: str, media_type: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if media_type == "image":
        return suffix if suffix in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    return suffix if suffix in (".mp4", ".mov", ".webm", ".m4v", ".ogv") else ".mp4"


def _fetch_option(folder: Path, option: dict[str, Any]) -> Path:
    if option.get("local_file"):
        path = folder / option["local_file"]
        if not path.exists():
            raise RuntimeError("arquivo enviado não foi encontrado")
        return path
    media_type = option.get("media_type", "video")
    url = option["download_url"]
    media_dir = folder / "media"
    media_dir.mkdir(exist_ok=True)
    dest = media_dir / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}{_ext_for(url, media_type)}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    import os
    if option.get("provider") == "YouTube" or "youtube.com" in url or "youtu.be" in url:
        import youtube_mgr
        youtube_mgr.download_youtube_video(url, dest)
        return dest
    if option.get("provider") == "Unsplash" and option.get("download_location"):
        key = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
        if key:  # a API exige avisar o download quando a imagem é usada
            requests.get(option["download_location"], headers={"Authorization": f"Client-ID {key}"}, timeout=25).raise_for_status()
    if option.get("provider") == "Coverr":
        key = os.getenv("COVERR_API_KEY", "").strip()
        if key:
            requests.patch(f"https://api.coverr.co/videos/{option['id']}/stats/downloads", headers={"x-api-key": key}, timeout=25).raise_for_status()
    download_file(url, dest)
    return dest


def ensure_media(pid: str, T: Tracker, p0: int | None = 2, p1: int | None = 22) -> dict[str, dict[str, Any]]:
    """Baixa (ou reaproveita) a mídia escolhida de cada cena. Se uma falhar, tenta as outras opções."""
    state = read_state(pid)
    folder = project_dir(pid)
    scenes = sorted(state.get("scenes", []), key=lambda s: s["start"])
    results: dict[str, dict[str, Any]] = {}
    T.update(stage="download", status="running", detail=f"0 de {len(scenes)} cenas", progress=0, message="Baixando a mídia das cenas...",
             log=f"Baixando mídia de {len(scenes)} cenas (clipes já baixados são reaproveitados).")

    def work(idx: int, scene: dict[str, Any]):
        options = scene.get("options", [])
        selected = int(scene.get("selected", 0))
        order = ([selected] if 0 <= selected < len(options) else []) + [i for i in range(len(options)) if i != selected]
        for attempt, i in enumerate(order[:3]):
            try:
                path = _fetch_option(folder, options[i])
                info = probe_media(path)
                if not info["has_video"]:
                    raise RuntimeError("arquivo sem imagem")
                return idx, {"path": path, "media_type": options[i].get("media_type", "video"), "option_index": i, "info": info, "fallback": attempt > 0}
            except Exception as exc:
                T.log(f"Cena {idx + 1}: falha ao baixar de {options[i].get('provider', 'banco')} ({str(exc)[:110]}).", "warn", stage="download")
        return idx, None

    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(work, i, s) for i, s in enumerate(scenes) if s.get("options")]
        for future in as_completed(futures):
            T.check()
            idx, res = future.result()
            done += 1
            if res:
                results[scenes[idx]["id"]] = res
                if res["fallback"]:
                    T.log(f"Cena {idx + 1}: usei outra opção porque a escolhida falhou.", "warn", stage="download")
            pct = int(100 * done / max(1, len(futures)))
            T.update(stage="download", detail=f"{done} de {len(futures)} cenas", progress=pct, overall=(p0 + int((p1 - p0) * done / max(1, len(futures))) if p0 is not None and p1 is not None else None))
    missing = [s["id"] for s in scenes if s["id"] not in results]

    def save(s: dict[str, Any]) -> None:
        for sc in s.get("scenes", []):
            res = results.get(sc["id"])
            if res:
                sc["media_file"] = str(res["path"].relative_to(folder))
                sc["media_type"] = res["media_type"]
                sc["media_info"] = {k: res["info"][k] for k in ("duration", "width", "height")}
            else:
                sc["media_file"] = None
    patch_state(pid, save)
    suffix = f" ({len(missing)} cenas ficarão com fundo liso)" if missing else ""
    T.update(stage="download", status="done", detail=f"{len(results)} de {len(scenes)} cenas com mídia{suffix}", log=f"Mídia pronta: {len(results)} de {len(scenes)} cenas{suffix}.", level="warn" if missing else "info")
    return results


# ------------------------------------------------------------------ áudio

def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def music_path(audio: dict[str, Any]) -> Path | None:
    music_id = audio.get("music_id")
    if not music_id or not str(music_id).isalnum():
        return None
    for candidate in MUSIC_DIR.glob(f"{music_id}.*"):
        if candidate.suffix.lower() != ".json":
            return candidate
    return None


def build_mix_cmd(narration: Path, music: Path | None, audio: dict[str, Any], out: Path, duration: float, *, fmt: str = "m4a") -> list[str]:
    nv = _clamp(audio.get("narration_volume"), 0.0, 2.0, 1.0)
    mv = _clamp(audio.get("music_volume"), 0.0, 1.0, 0.14)
    cmd = [ffmpeg_path(), "-y", "-i", str(narration)]
    norm = ",loudnorm=I=-14:TP=-1.0:LRA=11" if audio.get("normalize") else ""
    prep = "aresample=48000,aformat=channel_layouts=stereo"
    if music is None:
        fc = f"[0:a]{prep},volume={nv}{norm}[aout]"
    else:
        if audio.get("loop", True):
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", str(music)]
        fade_in = _clamp(audio.get("fade_in"), 0, 15, 2.0)
        fade_out = _clamp(audio.get("fade_out"), 0, 15, 3.0)
        fades = ""
        if fade_in > 0:
            fades += f",afade=t=in:st=0:d={fade_in}"
        if fade_out > 0 and duration > fade_out * 1.5:
            fades += f",afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out}"
        mus = f"[1:a]{prep},volume={mv}{fades}[mus]"
        if audio.get("ducking", True):
            th, ratio = DUCK.get(audio.get("duck_level", "medium"), DUCK["medium"])
            fc = (f"[0:a]{prep},volume={nv},asplit=2[nm][ns];{mus};"
                  f"[mus][ns]sidechaincompress=threshold={th}:ratio={ratio}:attack=30:release=500:makeup=1[duck];"
                  f"[nm][duck]amix=inputs=2:duration=first:dropout_transition=0,volume=2,alimiter=limit=0.95{norm}[aout]")
        else:
            fc = (f"[0:a]{prep},volume={nv}[nm];{mus};"
                  f"[nm][mus]amix=inputs=2:duration=first:dropout_transition=0,volume=2,alimiter=limit=0.95{norm}[aout]")
    cmd += ["-filter_complex", fc, "-map", "[aout]", "-t", f"{duration:.3f}"]
    if fmt == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", "160k"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-ar", "48000", str(out)]
    return cmd


# ------------------------------------------------------------------ corte de silêncios

def cortar_silencios(audio_path: Path, limiar: str = "-50dB", pausa_maxima: float = 0.25,
                     work_dir: Path | None = None) -> tuple[Path, float]:
    """Remove silêncios longos do áudio usando FFmpeg silenceremove.

    Devolve (caminho_do_audio_cortado, nova_duracao_em_segundos).
    Se não houver silêncios para cortar ou houver erro, devolve o original.
    """
    dest_dir = work_dir or audio_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"narracao_cortada_{audio_path.stem}.m4a"

    filtro = (
        f"silenceremove=start_periods=1:start_threshold={limiar}:start_silence=0.1:"
        f"stop_periods=-1:stop_duration={pausa_maxima:.2f}:stop_threshold={limiar}:stop_silence=0.25"
    )
    cmd = [
        ffmpeg_path(), "-y", "-i", str(audio_path),
        "-af", filtro,
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", str(out),
    ]
    try:
        run_ffmpeg(cmd, timeout=max(300, int(media_duration(audio_path) * 5)), cancel_check=lambda: False)
        if out.exists() and out.stat().st_size > 1000:
            nova_duracao = media_duration(out)
            return out, nova_duracao
    except Exception:
        pass
    return audio_path, media_duration(audio_path)


# ------------------------------------------------------------------ render

def render_project(pid: str) -> None:
    T = Tracker(pid)
    try:
        state = read_state(pid)
        folder = project_dir(pid)
        settings = state.get("settings", {})
        style = styles.resolve_style(settings.get("template"), settings.get("style"))
        ratio = settings.get("ratio", "16:9")
        width, height = styles.ratio_dimensions(ratio, settings.get("quality", "720p"))
        audio_opts = settings.get("audio", {})

        def reset(s: dict[str, Any]) -> None:
            stages = s.setdefault("stages", default_stages())
            for key in ("download", "segments", "join", "audio", "finish", "capcut"):
                stages[key] = default_stages()[key]
            stages["review"].update({"status": "done", "detail": "Cenas confirmadas", "ended": now_iso()})
            s.update({"status": "rendering", "progress": 0, "message": "Preparando...", "error": None, "cancel_requested": False, "output_file": None, "render_started": now_iso()})
            s["log"] = s.get("log", [])
        patch_state(pid, reset)
        T.log(f"Render iniciado · template «{styles.TEMPLATE_INDEX.get(settings.get('template'), {}).get('name', 'Padrão')}» · {width}x{height}.", stage="review")

        ffmpeg = ffmpeg_path()
        audio_path = folder / state["audio_file"]
        srt_path = folder / state["srt_file"]
        if not audio_path.exists() or not srt_path.exists():
            raise RuntimeError("O áudio ou o arquivo SRT não foi encontrado no projeto.")

        # Corte de silêncios (se habilitado na config de montagem)
        montagem_cfg = project_config.load_config(pid).get("montagem", {})
        if montagem_cfg.get("cortar_silencios", True):
            limiar = montagem_cfg.get("silencia_limiar", "-50dB")
            pausa_max = montagem_cfg.get("silencia_pausa_maxima", 0.25)
            T.log("Cortando silêncios da narração…", stage="audio")
            audio_path, audio_len = cortar_silencios(
                audio_path, limiar=limiar, pausa_maxima=pausa_max,
                work_dir=folder / "render_work",
            )
            T.log(f"Áudio cortado: {audio_len:.1f}s.", stage="audio")
        else:
            audio_len = media_duration(audio_path)
        scenes = sorted(state.get("scenes", []), key=lambda s: s["start"])
        if not scenes:
            raise RuntimeError("Nenhuma cena foi encontrada. Reenvie um arquivo SRT válido.")

        # cada cena vai até o início da próxima; contagem em frames inteiros evita deriva de sincronia
        for i, scene in enumerate(scenes):
            start = 0.0 if i == 0 else float(scene["start"])
            nxt = float(scenes[i + 1]["start"]) if i + 1 < len(scenes) else audio_len
            scene["render_start"] = max(0.0, start)
            scene["render_end"] = min(audio_len, max(scene["render_start"] + 0.25, nxt))
        boundaries = [round(s["render_start"] * FPS) for s in scenes] + [round(audio_len * FPS)]
        transition = str(style.get("transition", "cut"))
        tr_info = styles.TRANSITIONS.get(transition, styles.TRANSITIONS["cut"])
        use_xfade = bool(tr_info.get("mode") == "xfade" and len(scenes) > 1 and ffmpeg_has_filter("xfade"))
        xfade_dur = 0.0
        if use_xfade:
            min_slot = min(max(0.1, (boundaries[i + 1] - boundaries[i]) / FPS) for i in range(len(scenes)))
            xfade_dur = max(0.05, min(float(style.get("transition_dur", 0.35)), min_slot / 3, 1.5))
            T.log(f"Transição «{tr_info['label']}» entre as cenas ({xfade_dur:.2f} s).", stage="join")

        media = ensure_media(pid, T, 2, 22)
        T.check()

        work = folder / "render_work"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(exist_ok=True)

        # --- clipes com o estilo
        T.update(stage="segments", status="running", detail=f"0 de {len(scenes)} clipes", progress=0, message="Montando os clipes com o estilo escolhido...", log="Aplicando cor, movimento e transições em cada cena.")
        segments: list[Path] = []
        for idx, scene in enumerate(scenes):
            T.check()
            frames = max(6, boundaries[idx + 1] - boundaries[idx])
            segment = work / f"segment_{idx:04d}.mp4"
            info = media.get(scene["id"])
            out_args = ["-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS), "-video_track_timescale", "12288", str(segment)]
            if info:
                is_image = info["media_type"] == "image" or (info["info"]["duration"] <= 0.1)
                vf, needs_loop = styles.segment_filter(style, width, height, FPS, frames, idx, is_image=is_image, first=idx == 0, last=idx == len(scenes) - 1, ratio=ratio)
                if is_image:
                    inp = ["-loop", "1", "-i", str(info["path"])] if needs_loop else ["-i", str(info["path"])]
                else:
                    inp = ["-stream_loop", "-1", "-i", str(info["path"])]
                cmd = [ffmpeg, "-y", *inp, "-vf", vf, "-frames:v", str(frames), *out_args]
            else:
                base = f"color=c=0x18202d:s={width}x{height}:r={FPS},format=yuv420p"
                cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", base, "-frames:v", str(frames), *out_args]
                T.log(f"Cena {idx + 1}: sem mídia, usando fundo liso.", "warn", stage="segments")
            run_ffmpeg(cmd, timeout=20 * 60, cancel_check=T.cancelled)
            segments.append(segment)
            T.update(stage="segments", detail=f"{idx + 1} de {len(scenes)} clipes", progress=int(100 * (idx + 1) / len(scenes)), overall=22 + int(40 * (idx + 1) / len(scenes)))
        T.update(stage="segments", status="done", detail=f"{len(scenes)} clipes prontos", log=f"{len(scenes)} clipes montados.")

        # --- junta
        T.update(stage="join", status="running", detail="Unindo clipes", overall=63, message="Unindo a timeline...")
        joined = work / "joined.mp4"
        joined_ok = False
        if use_xfade:
            chain: list[str] = []
            inputs: list[str] = []
            for i, segment in enumerate(segments):
                inputs += ["-i", str(segment)]
                prep = f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={FPS},format=yuv420p"
                if i < len(segments) - 1:
                    prep += f",tpad=stop_mode=clone:stop_duration={xfade_dur:.3f}"
                chain.append(prep + f"[v{i}]")
            prev = "[v0]"
            for i in range(1, len(segments)):
                offset = boundaries[i] / FPS
                out_label = "[vout]" if i == len(segments) - 1 else f"[x{i}]"
                chain.append(f"{prev}[v{i}]xfade=transition={tr_info['xfade']}:duration={xfade_dur:.3f}:offset={offset:.3f}{out_label}")
                prev = out_label
            cmd = [ffmpeg, "-y", *inputs, "-filter_complex", ";".join(chain), "-map", "[vout]", "-an",
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
                   "-r", str(FPS), "-video_track_timescale", "12288", str(joined)]
            try:
                run_ffmpeg(cmd, timeout=40 * 60, cancel_check=T.cancelled)
                joined_ok = joined.exists() and joined.stat().st_size > 0
            except Exception as exc:
                if isinstance(exc, Cancelled):
                    raise
                T.log(f"A transição {tr_info.get('label', transition)} falhou; voltando para corte seco ({str(exc)[:120]}).", "warn", stage="join")
        if not joined_ok:
            concat_file = work / "concat.txt"
            concat_file.write_text("\n".join("file '" + str(p).replace("'", "'\\''") + "'" for p in segments), encoding="utf-8")
            run_ffmpeg([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(joined)], timeout=30 * 60, cancel_check=T.cancelled)
        T.update(stage="join", status="done", detail="Timeline pronta", progress=100, overall=67, log="Timeline unida.")

        # --- áudio
        mus = music_path(audio_opts)
        T.update(stage="audio", status="running", detail="Mixando narração e música" if mus else "Ajustando a narração", progress=0, overall=68, message="Mixando o áudio...",
                 log=("Mix: narração " + f"{int(float(audio_opts.get('narration_volume', 1)) * 100)}%" + (f", música {int(float(audio_opts.get('music_volume', 0.14)) * 100)}%" + (" com ducking" if audio_opts.get("ducking", True) else "") if mus else ", sem música") + "."))
        if audio_opts.get("music_id") and not mus:
            T.log("A música escolhida não está mais na biblioteca; o vídeo sai só com a narração.", "warn", stage="audio")
        mix = work / "mix.m4a"
        run_ffmpeg(build_mix_cmd(audio_path, mus, audio_opts, mix, audio_len), total=audio_len,
                   on_progress=lambda f: T.update(stage="audio", progress=int(f * 100), overall=68 + int(7 * f)),
                   timeout=max(600, int(audio_len * 6)), cancel_check=T.cancelled)
        T.update(stage="audio", status="done", detail="Áudio mixado", log="Áudio pronto.")

        # --- legendas + exportação
        output = folder / "video_final.mp4"
        vf = ""
        subs = style["subtitles"]
        if subs.get("enabled", True) or styles.has_overlays(style):
            if ffmpeg_has_filter("ass"):
                cues = parse_srt(srt_path.read_text(encoding="utf-8-sig", errors="replace"))
                ass_path = work / "subs.ass"
                ass_path.write_text(styles.build_ass(cues, style, width, height, ratio, scenes), encoding="utf-8")
                vf = styles.subtitles_filter(ass_path)
            else:
                T.log("Este FFmpeg não tem suporte a legendas (libass). O vídeo sai sem legenda queimada.", "warn", stage="finish")
        T.update(stage="finish", status="running", detail="Gravando legendas e exportando" if vf else "Exportando sem legendas", progress=0, overall=76, message="Exportando o MP4...",
                 log="Queimando as legendas e gravando o MP4." if vf else "Gravando o MP4 (sem legenda queimada).")
        cmd = [ffmpeg, "-y", "-i", str(joined), "-i", str(mix)]

        # Fade início/fim (se habilitado na montagem)
        fade_vf = ""
        fade_af = ""
        if montagem_cfg.get("fade_inicio_fim", True):
            fade_dur = 1.0
            fade_out_st = max(0.0, audio_len - fade_dur)
            fade_vf = f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={fade_out_st:.3f}:d={fade_dur}"
            fade_af = f"afade=t=in:st=0:d={fade_dur},afade=t=out:st={fade_out_st:.3f}:d={fade_dur}"

        if vf:
            vf_completo = f"{vf},{fade_vf}" if fade_vf else vf
            cmd += ["-vf", vf_completo, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
        else:
            if fade_vf:
                cmd += ["-vf", fade_vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
            else:
                cmd += ["-c:v", "copy"]
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy"]
        if fade_af:
            cmd += ["-af", fade_af]
        cmd += ["-t", f"{audio_len:.3f}", "-movflags", "+faststart", str(output)]
        run_ffmpeg(cmd, total=audio_len, on_progress=lambda f: T.update(stage="finish", progress=int(f * 100), overall=76 + int(22 * f)),
                   timeout=max(3600, int(audio_len * 15)), cancel_check=T.cancelled)
        size_mb = output.stat().st_size / 1024 / 1024
        T.update(stage="finish", status="done", detail=f"MP4 de {size_mb:.0f} MB", log=f"MP4 pronto ({size_mb:.0f} MB).")
        shutil.rmtree(work, ignore_errors=True)

        found = sum(1 for s in scenes if s["id"] in media)
        T.update(status="complete", overall=100 if not settings.get("auto_capcut") else 99, message="Vídeo concluído e pronto para baixar.",
                 output_file=output.name, audio_duration=round(audio_len, 2), scenes_with_footage=found)

        if settings.get("auto_capcut"):
            try:
                import capcut
                capcut.build_capcut_package(pid, T)
            except Cancelled:
                raise
            except Exception as exc:
                T.update(stage="capcut", status="failed", detail=str(exc)[:200], log=f"Não consegui montar o projeto do CapCut: {exc}", level="error")
            T.update(overall=100)
        T.log("Tudo pronto.", stage="finish")
    except Cancelled:
        def back(s: dict[str, Any]) -> None:
            s["status"] = "ready"
            s["message"] = "Render cancelado. Suas escolhas foram mantidas."
            s["cancel_requested"] = False
            for st in s.get("stages", {}).values():
                if st["status"] == "running":
                    st["status"] = "pending"
        patch_state(pid, back)
        T.log("Render cancelado por você.", "warn")
        shutil.rmtree(project_dir(pid) / "render_work", ignore_errors=True)
    except subprocess.TimeoutExpired:
        _fail(T, "O servidor demorou demais para concluir. Tente 720p ou um vídeo menor.")
    except Exception as exc:
        _fail(T, str(exc))


def _fail(T: Tracker, message: str) -> None:
    def fn(s: dict[str, Any]) -> None:
        s["status"] = "failed"
        s["error"] = message
        s["message"] = message
        for st in s.get("stages", {}).values():
            if st["status"] == "running":
                st["status"] = "failed"
                st["detail"] = message[:200]
    patch_state(T.pid, fn)
    T.log(message[:600], "error")
