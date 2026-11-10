"""Busca e download de vídeos do YouTube com yt-dlp e YouTube Data API."""
from __future__ import annotations

import hashlib
import json
import os
import re
import requests
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from store import DATA_DIR, ffmpeg_path, media_duration

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
                    "license": "YouTube · direitos não verificados; requer autorização antes de importar",
                    "preview_only": True,
                    "requires_permission": True,
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




def _youtube_video_duration(url: str) -> float:
    """Lê somente os metadados públicos do vídeo; não baixa o arquivo."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    try:
        return float(info.get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0


def _seconds(value: Any) -> float:
    """Converte segundos ou HH:MM:SS para segundos."""
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("timestamp ausente")
    if ":" not in raw:
        return float(raw)
    parts = [float(part) for part in raw.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError("timestamp inválido")


def locate_youtube_moment(
    url_or_id: str,
    narration_text: str,
    model: str | None = None,
    max_seconds: int = 10,
    context: str = "",
) -> dict[str, Any]:
    """Localiza com OpenRouter o melhor intervalo do vídeo para a fala exata do SRT."""
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Configure OPENROUTER_API_KEY para localizar o momento no vídeo.")
    video_id = extract_video_id(url_or_id)
    if not video_id:
        raise ValueError("Link do YouTube inválido.")
    url = f"https://www.youtube.com/watch?v={video_id}"
    limit = max(1, min(10, int(max_seconds or 10)))
    narration = " ".join(str(narration_text or "").split())[:1600]
    if not narration:
        raise ValueError("A cena não possui texto do SRT para comparar.")

    source_duration = _youtube_video_duration(url)
    if source_duration <= 0:
        raise RuntimeError("Não foi possível confirmar a duração do vídeo.")
    selected_model = (model or os.getenv("OPENROUTER_VISION_MODEL") or "google/gemini-2.5-flash").strip()
    prompt = (
        "Você é um editor de vídeo documental. Analise a linha do tempo do vídeo e encontre "
        "UM único trecho contínuo que melhor represente visualmente a fala atual. Priorize a ação "
        "e o significado exato, não apenas palavras parecidas. Escolha quando a ação está visível; "
        "evite introduções, créditos, tela preta e partes sem relação. Use os segundos contados "
        "desde o início do vídeo. Não invente timestamps: navegue na linha do tempo e use o tempo "
        "real observado. O intervalo deve ter entre 1 segundo e " + str(limit) + " segundos. "
        "Se nenhuma cena mostrar algo relacionado, retorne match=false. Responda somente JSON com "
        "match (boolean), start_seconds (número), end_seconds (número), confidence (0 a 1), "
        "reason (frase em português) e visual_summary (frase)."
        "\n\nFALA EXATA DO SRT:\n" + narration +
        "\n\nCONTEXTO VIZINHO (somente para desambiguar):\n" +
        (" ".join(str(context or "").split())[:1800] or "Não fornecido") +
        "\n\nDURAÇÃO TOTAL DO VÍDEO: " + f"{source_duration:.2f}" + " segundos."
    )
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-OpenRouter-Title": "FACELESS STUDIO",
        },
        json={
            "model": selected_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "video_url": {"url": url, "processing": "agentic"}},
                ],
            }],
            "temperature": 0.1,
            "max_tokens": 500,
        },
        timeout=(25, 240),
    )
    response.raise_for_status()
    payload = response.json()
    message = (((payload.get("choices") or [{}])[0].get("message")) or {})
    raw = message.get("content") or ""
    if isinstance(raw, list):
        raw = " ".join(
            str(part.get("text") or "") for part in raw
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    raw = str(raw).strip()
    first, last = raw.find("{"), raw.rfind("}")
    if first < 0 or last <= first:
        raise RuntimeError("O OpenRouter não devolveu um intervalo de cena em JSON válido.")
    try:
        result = json.loads(raw[first:last + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("A resposta de localização não é um JSON válido.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("A resposta do OpenRouter não contém um objeto de cena.")
    if result.get("match") is not True:
        raise RuntimeError(str(result.get("reason") or "Não foi encontrada uma cena compatível.")[:220])
    try:
        start = _seconds(result.get("start_seconds"))
        end = _seconds(result.get("end_seconds"))
        confidence = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("O OpenRouter retornou timestamps inválidos.") from exc
    if start < 0 or start >= source_duration or end <= start:
        raise RuntimeError("O intervalo encontrado está fora da duração real do vídeo.")
    end = min(end, start + limit, source_duration)
    if end - start < 0.8:
        raise RuntimeError("O trecho encontrado é curto demais para montar uma cena.")
    return {
        "video_id": video_id,
        "url": url,
        "video_duration": source_duration,
        "start_seconds": round(start, 3),
        "end_seconds": round(end, 3),
        "duration": round(end - start, 3),
        "confidence": round(confidence, 3),
        "reason": str(result.get("reason") or "")[:240],
        "visual_summary": str(result.get("visual_summary") or "")[:240],
        "model": selected_model,
    }


def download_youtube_clip(
    url_or_id: str,
    dest: Path,
    start_seconds: float,
    clip_seconds: float,
    max_duration: int = 10,
) -> Path:
    """Baixa o intervalo selecionado (não o início do vídeo) e valida o teto de 10 s."""
    import yt_dlp

    limit = max(1, min(10, int(max_duration or 10)))
    start = max(0.0, float(start_seconds or 0))
    length = min(float(clip_seconds or 0), float(limit))
    video_id = extract_video_id(url_or_id)
    if not video_id:
        raise ValueError("Link do YouTube inválido.")
    if length < 0.8:
        raise ValueError("O trecho precisa ter pelo menos 0,8 segundo.")
    ffmpeg = ffmpeg_path()
    if not ffmpeg or not Path(ffmpeg).exists():
        raise RuntimeError("FFmpeg é necessário para recortar o trecho do YouTube.")

    url = f"https://www.youtube.com/watch?v={video_id}"
    cache_id = hashlib.sha1(f"{video_id}|{start:.3f}|{length:.3f}|{limit}".encode("utf-8")).hexdigest()[:18]
    cached = YOUTUBE_CACHE_DIR / f"scene_{cache_id}.mp4"
    if cached.exists() and 0 < float(media_duration(cached) or 0) <= limit + 0.15:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, dest)
        return dest

    prefix = f"section_{cache_id}_{int(time.time() * 1000)}"
    output_template = str(YOUTUBE_CACHE_DIR / (prefix + ".%(ext)s"))

    def selected_range(_info: dict[str, Any], _ydl: Any) -> list[dict[str, Any]]:
        return [{"start_time": start, "end_time": start + length, "title": "scene", "index": 1}]

    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 35,
        "download_ranges": selected_range,
        "force_keyframes_at_cuts": True,
        "ffmpeg_location": str(Path(ffmpeg).parent),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = Path(ydl.prepare_filename(info))
            candidates = [
                item for item in YOUTUBE_CACHE_DIR.glob(prefix + "*")
                if item.is_file() and item.stat().st_size > 0
                and not item.name.endswith((".part", ".ytdl", ".json"))
            ]
            if prepared.exists() and prepared.is_file():
                candidates.insert(0, prepared)
            source_file = next((item for item in candidates if item.is_file() and item.stat().st_size > 0), None)
        if source_file is None:
            raise RuntimeError("O YouTube não entregou o trecho solicitado.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(ffmpeg), "-y", "-i", str(source_file),
            "-map", "0:v:0", "-an", "-t", f"{length:.3f}",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest),
        ]
        subprocess.run(command, capture_output=True, text=True, timeout=240, check=True)
        actual_duration = float(media_duration(dest) or 0)
        if not dest.exists() or dest.stat().st_size < 1024 or not (0.1 < actual_duration <= limit + 0.15):
            raise RuntimeError("O trecho final não passou na validação de duração de até dez segundos.")
        shutil.copy2(dest, cached)
        return dest
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        for item in YOUTUBE_CACHE_DIR.glob(prefix + "*"):
            if item.is_file():
                item.unlink(missing_ok=True)


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
        if duration <= 0:
            actual_file.unlink(missing_ok=True)
            raise RuntimeError("Não foi possível verificar a duração do vídeo; a regra de até dez segundos não pode ser garantida.")
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
