"""Busca e download de vídeos do YouTube com yt-dlp e YouTube Data API."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from store import DATA_DIR, ffmpeg_path

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

YOUTUBE_CACHE_DIR = DATA_DIR / "youtube_cache"
YOUTUBE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def extract_video_id(url_or_id: str) -> str | None:
    text = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    match = re.search(r"(?:v=|\/|youtu\.be\/)([A-Za-z0-9_-]{11})", text)
    return match.group(1) if match else None


# Palavras no título que indicam que NÃO é um clipe b-roll ilustrativo.
# Usadas para filtrar vídeos de música, talk-show, reaction, podcast, etc.
_YT_SKIP_TITLE_WORDS = {
    # Música
    "lyrics", "lyric", "letra", "karaoke", "music video", "mv", "official video",
    "official audio", "official music", "audio oficial", "clipe oficial", "clipe",
    "ft.", "feat.", "remix", "prod.", "prod by", "beat",
    # Talk-show / pessoas falando
    "podcast", "entrevista", "interview", "debate", "bate-papo", "conversa",
    "live", "ao vivo", "chat", "q&a",
    # Reaction / commentary
    "reaction", "reação", "reacting", "reagindo", "react", "commentary",
    "review", "análise", "análises", "unboxing", "haul",
    # Vlogs / tutoriais pessoais
    "vlog", "my day", "meu dia", "rotina", "minha rotina",
    "tutorial", "how to", "como fazer",
    # Compilados de memes/fail
    "fails", "memes", "compilation of fails", "try not to laugh",
    # Gameplay
    "gameplay", "gaming", "playing", "let's play",
}

# Palavras no canal que indicam canal de música/talk/reaction — rejeitar
_YT_SKIP_CHANNEL_WORDS = {
    "vevo", "records", "music", "músicas", "podcasts", "reacts",
    "reactions", "gaming", "games",
}


def _is_good_broll(title: str, channel: str, duration: float) -> bool:
    """Retorna True se o vídeo parece ser um clipe b-roll/documental adequado."""
    t = title.lower()
    c = channel.lower()
    # Rejeita por palavra no título
    for w in _YT_SKIP_TITLE_WORDS:
        if w in t:
            return False
    # Rejeita por palavra no canal
    for w in _YT_SKIP_CHANNEL_WORDS:
        if w in c:
            return False
    # Rejeita Shorts muito curtos (< 10s) e lives/vídeos absurdamente longos
    if 0 < duration < 10:
        return False
    if duration > 7200:  # > 2h → provavelmente live ou longa-metragem
        return False
    return True


def youtube_search(query: str, per: int = 4, orientation: str = "landscape") -> list[dict[str, Any]]:
    """Busca vídeos b-roll ilustrativos no YouTube com yt-dlp (sem chave de API).

    Usa termos de footage/cinematic para achar clipes visuais relevantes para a
    cena, filtra música/podcast/reaction e ordena por relevância do título.
    """
    import yt_dlp

    query_clean = query.strip()
    if not query_clean:
        return []

    cache_key = hashlib.sha256(f"yt|{query_clean.lower()}|{per}|{orientation}".encode("utf-8")).hexdigest()[:24]
    cache_file = YOUTUBE_CACHE_DIR / f"search_{cache_key}.json"
    try:
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 24 * 60 * 60:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached:
                return cached
    except (OSError, json.JSONDecodeError):
        pass

    # Monta termo de busca com qualificadores b-roll para clipes sem legendas/música
    if orientation == "portrait":
        broll_suffix = "vertical stock footage b-roll"
    else:
        broll_suffix = "stock footage b-roll cinematic 4k"

    # Evita duplicar se a query já tem termos de footage
    already_has_broll = any(w in query_clean.lower() for w in
                             ("b-roll", "broll", "footage", "cinematic", "stock", "documentary"))
    search_term = query_clean if already_has_broll else f"{query_clean} {broll_suffix}"

    limit = max(1, min(12, per))
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    stop = {"the", "and", "for", "with", "from", "this", "that", "com", "para", "dos", "das", "uma", "que"}
    query_words = {w for w in re.findall(r"[a-z0-9]+", query_clean.lower()) if len(w) > 2 and w not in stop}

    results: list[dict[str, Any]] = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Busca candidatos em dobro para compensar os filtrados
            data = ydl.extract_info(f"ytsearch{limit * 4}:{search_term}", download=False)
            entries = data.get("entries") or []

            for entry in entries:
                if not entry:
                    continue
                vid = entry.get("id")
                if not vid:
                    continue

                duration = float(entry.get("duration") or 0)
                title_orig = entry.get("title") or "Vídeo do YouTube"
                channel = entry.get("channel") or entry.get("uploader") or "YouTube"

                # Filtro de qualidade: só clipes b-roll/documentais adequados
                if not _is_good_broll(title_orig, channel, duration):
                    continue

                title_low = str(title_orig).lower()
                overlap = sum(1 for word in query_words if word in title_low)
                relevance = round(overlap / max(1, len(query_words)), 3)
                score = overlap * 2.0
                if 12 <= duration <= 240:
                    score += 2.0
                elif duration > 600:
                    score -= 1.0
                if any(w in title_low for w in ("b-roll", "broll", "footage", "cinematic", "documentary", "aerial", "drone")):
                    score += 1.5

                thumb = (
                    entry.get("thumbnail")
                    or (entry.get("thumbnails", [{}])[-1].get("url") if entry.get("thumbnails") else "")
                    or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                )

                results.append({
                    "id": f"yt_{vid}",
                    "provider": "YouTube",
                    "media_type": "video",
                    "download_url": f"https://www.youtube.com/watch?v={vid}",
                    "thumbnail": thumb,
                    "source_url": f"https://www.youtube.com/watch?v={vid}",
                    "photographer": channel[:80],
                    "license": "YouTube (Fair Use / Creative Commons)",
                    "width": 1280 if orientation != "portrait" else 720,
                    "height": 720 if orientation != "portrait" else 1280,
                    "duration": round(duration, 1) if duration else None,
                    "title": title_orig[:100],
                    "description": str(entry.get("description") or "")[:240],
                    "tags": [query_clean[:60]],
                    "relevance": relevance,
                    "video_id": vid,
                    "_score": round(score, 2),
                })
    except Exception:
        pass

    results.sort(key=lambda item: (-float(item.get("_score") or 0), -float(item.get("relevance") or 0)))
    for item in results:
        item.pop("_score", None)
    results = results[:limit]
    if results:
        try:
            cache_file.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return results


def download_youtube_video(url_or_id: str, dest: Path, max_duration: int = 10) -> Path:
    """Obtém um clipe autorizado e aplica limite rígido de até dez segundos."""
    import yt_dlp

    max_duration = max(1, min(10, int(max_duration or 10)))
    vid = extract_video_id(url_or_id)
    url = f"https://www.youtube.com/watch?v={vid}" if vid else url_or_id.strip()

    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    cached_file = YOUTUBE_CACHE_DIR / f"{url_hash}_{max_duration}s.mp4"

    def duration_of(path: Path) -> float:
        try:
            import json as _json
            result = subprocess.run(
                [ffmpeg_path().replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe"),
                 "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                capture_output=True, text=True, timeout=20, check=True,
            )
            return float((_json.loads(result.stdout).get("format") or {}).get("duration") or 0)
        except Exception:
            return 0.0

    if cached_file.exists() and cached_file.stat().st_size > 50_000:
        cached_duration = duration_of(cached_file)
        if 0 < cached_duration <= max_duration + 0.15:
            shutil.copy2(cached_file, dest)
            return dest
        cached_file.unlink(missing_ok=True)

    temp_tmpl = str(YOUTUBE_CACHE_DIR / f"tmp_{url_hash}_%(id)s.%(ext)s")
    ffmpeg_bin = ffmpeg_path()
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": temp_tmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    if ffmpeg_bin and Path(ffmpeg_bin).exists():
        ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_bin).parent)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        actual_file = Path(filename)
        if not actual_file.exists():
            candidate = actual_file.with_suffix(".mp4")
            if candidate.exists():
                actual_file = candidate

        if not actual_file.exists() or actual_file.stat().st_size == 0:
            raise RuntimeError(f"Não foi possível obter o clipe autorizado do YouTube: {url}")

        duration = duration_of(actual_file)
        if duration <= 0:
            duration = float(info.get("duration") or 0)
        if duration > max_duration + 0.15:
            if not ffmpeg_bin or not Path(ffmpeg_bin).exists():
                actual_file.unlink(missing_ok=True)
                raise RuntimeError("FFmpeg é necessário para limitar este vídeo a até dez segundos.")
            clip_path = YOUTUBE_CACHE_DIR / f"clip_{url_hash}_{max_duration}s.mp4"
            try:
                subprocess.run(
                    [ffmpeg_bin, "-y", "-i", str(actual_file), "-t", str(max_duration),
                     "-map", "0:v:0", "-an", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                     "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
                     "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(clip_path)],
                    capture_output=True, text=True, timeout=180, check=True,
                )
                clip_duration = duration_of(clip_path)
                if not clip_path.exists() or clip_path.stat().st_size < 1024 or not (0 < clip_duration <= max_duration + 0.15):
                    raise RuntimeError("O clipe final não passou na validação de duração.")
                clip_path.replace(cached_file)
            except Exception:
                clip_path.unlink(missing_ok=True)
                actual_file.unlink(missing_ok=True)
                raise
            actual_file.unlink(missing_ok=True)
        else:
            actual_file.replace(cached_file)

    shutil.copy2(cached_file, dest)
    return dest
