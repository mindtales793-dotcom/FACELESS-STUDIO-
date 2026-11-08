"""Transcrição de áudio com Groq (Whisper) e geração de SRT sincronizado.

Porta para dentro do estúdio as funções do separador DarkCut SRT:

* compressão e segmentação de áudios acima de 24 MB (limite da API Groq);
* transcrição com ``verbose_json`` e horários por palavra;
* montagem de SRT a partir das palavras reconhecidas;
* alinhamento do roteiro original aos horários reconhecidos (sem trocar o texto);
* detecção de pausas com FFmpeg para melhorar os cortes das legendas;
* fila de tarefas em disco com progresso, cache por hash do áudio e aplicação
  automática das legendas em um projeto existente.

O módulo não guarda a chave: ela vem de ``GROQ_API_KEY`` / tela de Chaves.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests

from store import DATA_DIR, ffmpeg_path, media_duration, now_iso, patch_state, project_dir, read_state

API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
API_LIMIT = int(os.getenv("GROQ_API_LIMIT_MB", "24")) * 1024 * 1024
MAX_UPLOAD = int(os.getenv("GROQ_MAX_UPLOAD_MB", "250")) * 1024 * 1024
MAX_ACTIVE_JOBS = int(os.getenv("GROQ_MAX_ACTIVE_JOBS", "2"))
ALLOWED_MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")
DEFAULT_MODEL = "whisper-large-v3-turbo"
ALLOWED_MODES = ("auto", "words", "script")

MODELS = [
    {"id": "whisper-large-v3-turbo", "label": "Whisper Large v3 Turbo", "hint": "Rápido e econômico. Recomendado para narração limpa."},
    {"id": "whisper-large-v3", "label": "Whisper Large v3", "hint": "Mais preciso em áudios difíceis; um pouco mais lento."},
]

LANGUAGES = [
    {"id": "auto", "label": "Detectar automaticamente"},
    {"id": "pt", "label": "Português"},
    {"id": "en", "label": "Inglês"},
    {"id": "es", "label": "Espanhol"},
    {"id": "fr", "label": "Francês"},
    {"id": "de", "label": "Alemão"},
    {"id": "it", "label": "Italiano"},
]

AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".webm", ".mov")

JOBS_DIR = DATA_DIR / "transcriptions"
CACHE_DIR = JOBS_DIR / "cache"
_LOCK = threading.RLock()


# ------------------------------------------------------------------ utilitários

def groq_key() -> str:
    """Chave Groq configurada no ambiente (nunca é devolvida para a interface)."""
    return os.getenv("GROQ_API_KEY", "").strip()


def has_key() -> bool:
    value = groq_key()
    if not value:
        return False
    low = value.lower()
    return bool(value) and not low.startswith(("sua_", "your_", "troque_por", "coloque_aqui", "insira_aqui"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_duration(path: Path) -> float:
    try:
        return max(0.0, float(media_duration(path)))
    except Exception:
        return 0.0


def _clean_script(text: str) -> str:
    """Remove marcações comuns de roteiro sem alterar as palavras faladas."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*(?:#{1,6}\s*|[-*•–—]\s*|\d+[.)]\s*)", "", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def normalize_speech_word(value: Any) -> str:
    """Normaliza uma palavra para comparação (sem acento, caixa ou pontuação)."""
    text = str(value or "").lower()
    try:
        import unicodedata
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    except Exception:
        pass
    return re.sub(r"[^a-z0-9]", "", text)


def to_srt_time(seconds: float) -> str:
    ms_total = max(0, int(round(float(seconds) * 1000)))
    h, m = ms_total // 3600000, (ms_total % 3600000) // 60000
    s, ms = (ms_total % 60000) // 1000, ms_total % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def tokenise_text(text: str) -> list[str]:
    """Separa o roteiro por pontuação (e quebras de linha), mantendo os sinais."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"([.,!?…;:]+|[\n]+)", text)
    segments: list[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"[.,!?…;:]+", part):
            current += part
            clean = current.strip()
            if clean:
                segments.append(clean)
            current = ""
        elif re.fullmatch(r"[\n]+", part):
            clean = current.strip()
            if clean:
                segments.append(clean)
            current = ""
        else:
            current += part
    if current.strip():
        segments.append(current.strip())
    return [s for s in (x.strip() for x in segments) if s]


def split_into_halves(words: list[str], limit: int) -> list[str]:
    if len(words) <= limit:
        return [" ".join(words)]
    mid = max(1, math.ceil(len(words) / 2))
    return split_into_halves(words[:mid], limit) + split_into_halves(words[mid:], limit)


def build_blocks(segments: list[str], limit: int) -> list[str]:
    blocks: list[str] = []
    for segment in segments:
        words = segment.split()
        if not words:
            continue
        if len(words) <= limit:
            blocks.append(" ".join(words))
        else:
            blocks.extend(split_into_halves(words, limit))
    return [b for b in (x.strip() for x in blocks) if b]


def merge_small_blocks(blocks: list[str], min_words: int, max_words: int) -> list[str]:
    merged: list[str] = []
    pending = ""
    for i, block in enumerate(blocks):
        combined = f"{pending} {block}".strip() if pending else block
        count = len(combined.split())
        if count < min_words and i < len(blocks) - 1:
            pending = combined
        else:
            merged.append(combined.strip())
            pending = ""
    if pending:
        if merged:
            merged[-1] = f"{merged[-1]} {pending}".strip()
        else:
            merged.append(pending.strip())
    final: list[str] = []
    for block in merged:
        words = block.split()
        if len(words) > max_words:
            final.extend(split_into_halves(words, max_words))
        else:
            final.append(block)
    return [b for b in (x.strip() for x in final) if b]


def estimate_cue_boundaries(blocks: list[str], *, start_secs: float = 0.0, secs_per_word: float = 0.4,
                            audio_duration: float = 0.0, pause_points: list[float] | None = None) -> list[int]:
    """Estima fronteiras em milissegundos proporcionais ao número de palavras."""
    weights = [max(1, len(block.split())) for block in blocks]
    total_words = sum(weights) or 1
    effective = audio_duration if audio_duration > 0 else total_words * secs_per_word
    start_ms = int(round(max(0.0, start_secs) * 1000))
    total_ms = max(1, int(round(effective * 1000)))
    cumulative = 0
    boundaries = [start_ms]
    for weight in weights:
        cumulative += weight
        boundaries.append(start_ms + int(round(total_ms * cumulative / total_words)))
    pauses = pause_points or []
    if pauses and len(blocks) > 1:
        for i in range(1, len(boundaries) - 1):
            target = boundaries[i]
            left, right = boundaries[i - 1], boundaries[i + 1]
            available = min((target - left) * 0.4, (right - target) * 0.4, 1200)
            if available < 90:
                continue
            low, high = max(left + 120, target - available), min(right - 120, target + available)
            best, difference = target, math.inf
            for pause in pauses:
                ms = start_ms + int(round(float(pause) * 1000))
                if ms < low or ms > high:
                    continue
                delta = abs(ms - target)
                if delta < difference:
                    difference, best = delta, ms
            boundaries[i] = best
    return boundaries


def align_script_blocks_to_words(blocks: list[str], words: list[dict[str, Any]], *,
                                 start_secs: float = 0.0, duration: float = 0.0) -> tuple[list[int], float]:
    """Alinha o roteiro original (monotônico) aos horários reconhecidos.

    Nenhuma palavra do roteiro é substituída: palavras não reconhecidas são
    interpoladas entre as âncoras encontradas. Devolve (fronteiras_ms, qualidade).
    """
    scripted = [w for b in blocks for w in b.split() if w]
    count = len(scripted)
    if count == 0 or not words:
        return [0, max(1, int(duration * 1000))], 0.0
    recognized = [normalize_speech_word(w.get("word")) for w in words]
    indexes = [-1] * count
    cursor = 0
    matches = 0
    for i, token in enumerate(scripted):
        target = normalize_speech_word(token)
        if not target:
            continue
        found = -1
        for k in range(cursor, min(len(recognized), cursor + 20)):
            if recognized[k] == target:
                found = k
                break
        if found >= 0:
            indexes[i] = found
            cursor = found + 1
            matches += 1

    duration_ms = max(1, int(round((duration or 0) * 1000)))
    start_ms = int(round(max(0.0, start_secs) * 1000))
    anchors: list[tuple[int, int]] = []
    for i, index in enumerate(indexes):
        if index >= 0:
            try:
                t = int(round(float(words[index].get("start", 0)) * 1000))
            except (TypeError, ValueError):
                continue
            anchors.append((i, max(0, min(duration_ms, t))))

    points = [(0, 0), *anchors, (count, duration_ms)]
    points.sort(key=lambda p: p[0])

    def interpolate(index: int) -> int:
        for k in range(1, len(points)):
            if points[k][0] >= index:
                prev_i, prev_t = points[k - 1]
                next_i, next_t = points[k]
                if next_i == prev_i:
                    return int(next_t)
                return int(round(prev_t + (next_t - prev_t) * (index - prev_i) / (next_i - prev_i)))
        return duration_ms

    raw = [0]
    cumulative = 0
    for block in blocks:
        cumulative += len(block.split())
        raw.append(interpolate(cumulative))
    raw[0], raw[-1] = 0, duration_ms

    boundaries = [start_ms]
    for index in range(1, len(raw) - 1):
        remaining = len(raw) - index - 1
        previous = boundaries[-1] - start_ms
        nxt = max(previous + 1, min(raw[index], duration_ms - remaining))
        boundaries.append(start_ms + nxt)
    boundaries.append(start_ms + duration_ms)
    return boundaries, matches / max(1, count)


# ------------------------------------------------------------------ áudio / API

def duration_from_ffprobe(path: Path) -> float:
    return _safe_duration(path)


def find_pause_points(src: Path, *, noise: str = "-32dB", min_silence: float = 0.18,
                      max_points: int = 4000) -> list[float]:
    """Detecta pausas com o silencedetect do FFmpeg (sem decodificar na memória)."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return []
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(src), "-af",
             f"silencedetect=noise={noise}:d={min_silence}", "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=240,
        )
    except Exception:
        return []
    points: list[float] = []
    for match in re.finditer(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)", proc.stderr or ""):
        try:
            points.append(float(match.group(1)))
        except ValueError:
            continue
        if len(points) >= max_points:
            break
    return points


def compress_and_partition(src: Path, dest_dir: Path) -> list[tuple[Path, float]]:
    """Garante partes abaixo de 24 MB. Devolve [(arquivo, deslocamento_em_segundos)]."""
    src = Path(src)
    if src.stat().st_size <= API_LIMIT:
        return [(src, 0.0)]
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise ValueError("O áudio passa de 24 MB e o FFmpeg não está disponível para comprimir. "
                         "Converta a narração para MP3 mono 48 kbps e tente novamente.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    compressed = dest_dir / "audio-comprimido.mp3"
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", str(compressed)],
        capture_output=True, text=True, errors="replace", timeout=900,
    )
    if result.returncode:
        raise ValueError("Falha ao preparar o áudio grande com FFmpeg: " + (result.stderr or "")[-250:])
    if compressed.stat().st_size <= API_LIMIT:
        return [(compressed, 0.0)]
    template = str(dest_dir / "parte-%03d.mp3")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(compressed),
         "-f", "segment", "-segment_time", "900", "-reset_timestamps", "1", "-c", "copy", template],
        capture_output=True, text=True, errors="replace", timeout=600,
    )
    if result.returncode:
        raise ValueError("Não foi possível dividir o áudio longo em partes.")
    chunks = sorted(dest_dir.glob("parte-*.mp3"))
    if not chunks or any(p.stat().st_size > API_LIMIT for p in chunks):
        raise ValueError("Não foi possível gerar partes menores que 24 MB.")
    output: list[tuple[Path, float]] = []
    offset = 0.0
    for part in chunks:
        output.append((part, offset))
        offset += duration_from_ffprobe(part) or 900.0
    return output


def _error_message(status: int, raw: str) -> str:
    message = f"Falha na transcrição (HTTP {status})."
    try:
        info = json.loads(raw)
        message = info.get("error", {}).get("message", message) or message
    except (ValueError, TypeError, AttributeError):
        pass
    if status == 401:
        return "Chave Groq inválida ou revogada. Cadastre novamente na tela de Chaves."
    if status == 403:
        return ("A Groq/Cloudflare bloqueou a requisição (HTTP 403). Verifique se a chave tem acesso "
                "ao modelo em console.groq.com > Limits e se não há VPN/proxy ativo.")
    if status == 413:
        return "Áudio acima do limite da conta Groq. O estúdio tenta comprimir, mas este arquivo ainda ficou grande."
    if status == 429:
        return "Limite temporário da Groq (HTTP 429). Aguarde alguns minutos e tente novamente."
    if status in (500, 502, 503, 504):
        return f"A Groq está temporariamente indisponível (HTTP {status}). Tente novamente."
    return message


def groq_transcribe(audio: Path, key: str, model: str, language: str = "auto") -> dict[str, Any]:
    """Envia uma parte para a API Groq e devolve o JSON ``verbose_json``."""
    if model not in ALLOWED_MODELS:
        raise ValueError("Modelo de transcrição inválido.")
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    }
    data: dict[str, str] = {
        "model": model,
        "response_format": "verbose_json",
        "temperature": "0",
        "timestamp_granularities[]": "word",
    }
    if language and language != "auto":
        data["language"] = language

    last_error = ""
    for attempt in range(3):
        try:
            with audio.open("rb") as handle:
                response = requests.post(
                    API_URL, headers=headers, data=data,
                    files={"file": (audio.name, handle, "application/octet-stream")},
                    timeout=(30, 600),
                )
        except requests.exceptions.RequestException as exc:
            last_error = f"Não foi possível acessar a API Groq: {type(exc).__name__}. Confira internet, proxy/firewall."
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise ValueError(last_error) from None

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError:
                raise ValueError("A Groq devolveu uma resposta que não é JSON.") from None
            if not isinstance(payload, dict):
                raise ValueError("Resposta inesperada da Groq (formato inválido).")
            return payload

        raw = response.text[:1200]
        message = _error_message(response.status_code, raw)
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            retry = response.headers.get("Retry-After", "").strip()
            try:
                delay = min(12.0, max(0.5, float(retry))) if retry else 1.5 * (attempt + 1)
            except ValueError:
                delay = 1.5 * (attempt + 1)
            time.sleep(delay)
            continue
        raise ValueError(message)
    raise ValueError(last_error or "A transcrição falhou.")


def do_transcription(src: Path, *, model: str = DEFAULT_MODEL, language: str = "auto",
                     on_progress: Callable[..., None] | None = None, use_cache: bool = True,
                     work_dir: Path | None = None) -> dict[str, Any]:
    """Transcreve o áudio inteiro, comprimindo/segmentando quando necessário."""
    key = groq_key()
    if not key:
        raise ValueError("Salve a chave Groq na tela de Chaves antes de transcrever.")
    if model not in ALLOWED_MODELS:
        raise ValueError("Modelo de transcrição inválido.")
    src = Path(src)

    cache_key = ""
    if use_cache:
        cache_key = hashlib.sha256(f"{_sha256_file(src)}|{model}|{language}".encode("utf-8")).hexdigest()
        cached = _cache_read(cache_key)
        if cached:
            if on_progress:
                on_progress(stage="finalizing", progress=88,
                            message=f"Transcrição reaproveitada do cache ({len(cached.get('words', []))} palavras).")
            cached["cached"] = True
            return cached

    if on_progress:
        on_progress(stage="preparing", progress=5, message="Preparando o áudio e verificando o tamanho…")
    temp_holder = None
    if work_dir is None:
        temp_holder = tempfile.TemporaryDirectory(prefix="groq-srt-")
        work_dir = Path(temp_holder.name)
    work_dir = Path(work_dir)
    try:
        parts = compress_and_partition(src, work_dir)
        total_parts = len(parts)
        transcript: list[str] = []
        words: list[dict[str, Any]] = []
        segments: list[dict[str, Any]] = []
        if on_progress:
            on_progress(stage="transcribing", progress=12, completed=0, total=total_parts,
                        message=f"Transcrevendo parte 1 de {total_parts}…")
        for index, (part, offset) in enumerate(parts, start=1):
            result = groq_transcribe(part, key, model, language)
            transcript.append(str(result.get("text") or "").strip())
            for word in (result.get("words") or []):
                try:
                    start = float(word["start"]) + offset
                    end = float(word["end"]) + offset
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
                text = str(word.get("word") or "").strip()
                if text and end >= start:
                    words.append({"word": text, "start": start, "end": end})
            for segment in (result.get("segments") or []):
                try:
                    segments.append({
                        "text": str(segment.get("text") or "").strip(),
                        "start": float(segment["start"]) + offset,
                        "end": float(segment["end"]) + offset,
                    })
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
            if on_progress:
                pct = 12 + int(72 * index / max(1, total_parts))
                on_progress(stage="transcribing", progress=pct, completed=index, total=total_parts,
                            message=f"Parte {index}/{total_parts} reconhecida.")
        if not words:
            raise ValueError("A API não retornou horários por palavra. Tente o modelo Whisper Large v3 "
                             "ou um áudio com fala mais clara.")
        if on_progress:
            on_progress(stage="finalizing", progress=88, completed=total_parts, total=total_parts,
                        message="Validando horários das palavras…")
        duration = max([float(w["end"]) for w in words] + [0.0]) or _safe_duration(src)
        payload = {
            "text": " ".join(transcript).strip(),
            "words": words,
            "segments": segments,
            "duration": round(duration, 3),
            "parts": total_parts,
            "model": model,
            "language": language,
            "cached": False,
            "created_at": now_iso(),
        }
        if cache_key and words:
            _cache_write(cache_key, payload)
        return payload
    finally:
        if temp_holder is not None:
            temp_holder.cleanup()


# ------------------------------------------------------------------ geração de SRT

def _group_words(words: list[dict[str, Any]], max_words: int, min_words: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        text = str(word.get("word") or "").strip()
        if not text:
            continue
        current.append(word)
        end_of_sentence = bool(re.search(r"[.!?…;:]$", text))
        if len(current) >= max_words or end_of_sentence:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    merged: list[list[dict[str, Any]]] = []
    pending: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        combined = pending + group
        if len(combined) < min_words and index < len(groups) - 1:
            pending = combined
        else:
            merged.append(combined)
            pending = []
    if pending:
        if merged:
            merged[-1].extend(pending)
        else:
            merged.append(pending)

    final: list[list[dict[str, Any]]] = []
    for group in merged:
        if len(group) > max_words:
            stack = [group]
            while stack:
                chunk = stack.pop(0)
                if len(chunk) <= max_words:
                    final.append(chunk)
                else:
                    mid = max(1, math.ceil(len(chunk) / 2))
                    stack.insert(0, chunk[:mid])
                    stack.insert(1, chunk[mid:])
        else:
            final.append(group)
    return [g for g in final if g]


def cues_from_words(words: list[dict[str, Any]], *, max_words: int = 20, min_words: int = 6,
                    duration: float = 0.0) -> list[dict[str, Any]]:
    """Monta blocos de legenda com os horários exatos das palavras."""
    limit = max(5, min(100, int(max_words)))
    minimum = max(1, min(limit, int(min_words)))
    groups = _group_words(words, limit, minimum)
    cues: list[dict[str, Any]] = []
    previous_end = 0.0
    for group in groups:
        text = " ".join(str(w.get("word") or "").strip() for w in group).strip()
        text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
        if not text:
            continue
        try:
            start = float(group[0].get("start", 0))
            end = float(group[-1].get("end", start))
        except (TypeError, ValueError):
            continue
        if duration > 0:
            start, end = min(start, duration), min(end, duration)
        start = max(start, previous_end)
        end = max(end, start + 0.25)
        if duration > 0:
            end = min(end, duration)
        cues.append({"text": text, "start": round(start, 3), "end": round(end, 3)})
        previous_end = end
    return cues


def cues_from_script(script: str, words: list[dict[str, Any]], *, word_limit: int = 20, word_min: int = 7,
                     start_secs: float = 0.0, duration: float = 0.0,
                     pause_points: list[float] | None = None) -> tuple[list[dict[str, Any]], float]:
    """Usa o roteiro original como texto das legendas e alinha aos horários."""
    limit = max(5, min(100, int(word_limit)))
    minimum = max(1, min(limit, int(word_min)))
    segments = tokenise_text(_clean_script(script))
    blocks = merge_small_blocks(build_blocks(segments, limit), minimum, limit)
    if not blocks:
        return [], 0.0
    total_ms = max([float(w.get("end", 0)) for w in words] + [0.0])
    duration = duration or total_ms
    boundaries, ratio = align_script_blocks_to_words(blocks, words, start_secs=start_secs, duration=duration)
    cues: list[dict[str, Any]] = []
    for i, block in enumerate(blocks):
        start = boundaries[i] / 1000.0
        end = boundaries[i + 1] / 1000.0
        if end - start < 0.05:
            end = start + 0.05
        cues.append({"text": block.strip(), "start": round(start, 3), "end": round(end, 3)})
    return cues, ratio


def cues_to_srt(cues: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        text = re.sub(r"[ \t]+", " ", str(cue.get("text") or "")).strip()
        if not text:
            continue
        start = max(0.0, float(cue.get("start") or 0))
        end = max(start + 0.001, float(cue.get("end") or start + 0.001))
        lines.extend([str(index), f"{to_srt_time(start)} --> {to_srt_time(end)}", text, ""])
    return "\n".join(lines).strip() + "\n" if lines else ""


def srt_from_words(words: list[dict[str, Any]], *, max_words: int = 20, min_words: int = 6,
                   duration: float = 0.0) -> str:
    return cues_to_srt(cues_from_words(words, max_words=max_words, min_words=min_words, duration=duration))


def srt_from_script(script: str, words: list[dict[str, Any]], *, word_limit: int = 20, word_min: int = 7,
                    start_secs: float = 0.0, duration: float = 0.0) -> tuple[str, float]:
    cues, ratio = cues_from_script(script, words, word_limit=word_limit, word_min=word_min,
                                   start_secs=start_secs, duration=duration)
    return cues_to_srt(cues), ratio


# ------------------------------------------------------------------ jobs em disco

def _cache_read(key: str) -> dict[str, Any] | None:
    path = CACHE_DIR / f"{key}.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("words"):
                return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _cache_write(key: str, payload: dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id or ""):
        raise FileNotFoundError("Tarefa de transcrição não encontrada.")
    return JOBS_DIR / job_id


def read_job(job_id: str) -> dict[str, Any]:
    path = job_dir(job_id) / "job.json"
    if not path.exists():
        raise FileNotFoundError("Tarefa de transcrição não encontrada. Verifique se o servidor foi reiniciado.")
    return json.loads(path.read_text(encoding="utf-8"))


def write_job(job_id: str, state: dict[str, Any]) -> None:
    folder = job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / "job.json.tmp"
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temp.replace(folder / "job.json")


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        state = read_job(job_id)
        state.update(fields)
        state["updated_at"] = now_iso()
        write_job(job_id, state)
        return state


def public_job(state: dict[str, Any]) -> dict[str, Any]:
    public = {k: v for k, v in state.items() if k not in ("audio_file", "script_text", "result")}
    if state.get("status") == "complete":
        job_id = state.get("id", "")
        public["srt_url"] = f"/api/transcribe/{job_id}/download/srt"
        public["txt_url"] = f"/api/transcribe/{job_id}/download/txt"
        public["json_url"] = f"/api/transcribe/{job_id}/download/json"
        if state.get("script_srt"):
            public["script_srt_url"] = f"/api/transcribe/{job_id}/download/script_srt"
    return public


def active_count() -> int:
    count = 0
    if not JOBS_DIR.exists():
        return 0
    for folder in JOBS_DIR.iterdir():
        if not folder.is_dir() or folder.name == "cache":
            continue
        try:
            state = json.loads((folder / "job.json").read_text(encoding="utf-8"))
            if state.get("status") in ("queued", "running"):
                count += 1
        except (OSError, json.JSONDecodeError):
            continue
    return count


def list_jobs(limit: int = 12) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if not JOBS_DIR.exists():
        return jobs
    for folder in JOBS_DIR.iterdir():
        if not folder.is_dir() or folder.name == "cache":
            continue
        try:
            state = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        brief = public_job(state)
        brief["text"] = str(brief.get("text") or "")[:240]
        jobs.append(brief)
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs[: max(1, limit)]


def create_job(audio_path: Path, *, model: str = DEFAULT_MODEL, language: str = "auto",
               script_text: str = "", mode: str = "auto", project_id: str | None = None,
               origin: str = "upload", name: str = "", seconds: float = 0.0) -> str:
    """Cria a tarefa, copia o áudio para a pasta dela e devolve o id."""
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL
    if mode not in ALLOWED_MODES:
        mode = "auto"
    job_id = uuid.uuid4().hex
    folder = job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    src = Path(audio_path)
    suffix = src.suffix.lower() if src.suffix.lower() in AUDIO_SUFFIXES else ".mp3"
    dest = folder / f"audio{suffix}"
    try:
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
    except OSError:
        dest = src
    state = {
        "id": job_id, "status": "queued", "stage": "uploading", "progress": 0,
        "message": "Áudio recebido. Preparando a transcrição…", "error": None,
        "model": model, "language": language, "mode": mode,
        "project_id": project_id, "origin": origin, "name": (name or src.name)[:120],
        "audio_file": dest.name, "script_text": _clean_script(script_text)[:200000],
        "duration": round(float(seconds or 0), 3), "word_count": 0,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    write_job(job_id, state)
    return job_id


def run_job(job_id: str) -> None:
    """Executa a tarefa em segundo plano e grava SRT/TXT/JSON no disco."""
    folder = job_dir(job_id)
    work = folder / "work"
    try:
        state = read_job(job_id)
        audio = folder / state.get("audio_file", "audio.mp3")
        if not audio.exists():
            raise ValueError("O arquivo de áudio da tarefa não foi encontrado.")
        update_job(job_id, status="running", stage="preparing", progress=3,
                   message="Preparando o áudio e verificando o tamanho…")

        def progress(**fields: Any) -> None:
            update_job(job_id, **fields)

        transcript = do_transcription(
            audio, model=state.get("model", DEFAULT_MODEL), language=state.get("language", "auto"),
            on_progress=progress, work_dir=work,
        )
        words = transcript.get("words") or []
        duration = float(transcript.get("duration") or _safe_duration(audio) or 0)
        update_job(job_id, stage="finalizing", progress=92, message="Montando as legendas sincronizadas…")

        words_srt = srt_from_words(words, max_words=20, min_words=6, duration=duration)
        if not words_srt:
            raise ValueError("Não foi possível montar o SRT: nenhuma palavra com horário válido.")
        (folder / "transcricao.srt").write_text(words_srt, encoding="utf-8")
        (folder / "transcricao.txt").write_text(str(transcript.get("text") or ""), encoding="utf-8")
        (folder / "transcricao.json").write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")

        script_srt = ""
        script_ratio = 0.0
        script_text = str(state.get("script_text") or "").strip()
        if script_text:
            try:
                script_srt, script_ratio = srt_from_script(
                    script_text, words, word_limit=20, word_min=7, duration=duration,
                )
                if script_srt and script_ratio >= 0.25:
                    (folder / "roteiro.srt").write_text(script_srt, encoding="utf-8")
                else:
                    script_srt = ""
            except Exception:
                script_srt = ""

        mode = state.get("mode", "auto")
        use_script = bool(script_srt) and mode in ("auto", "script") and script_ratio >= (0.55 if mode == "auto" else 0.4)
        chosen = "roteiro" if use_script else "transcricao"
        chosen_file = f"{chosen}.srt"
        srt_text = (folder / chosen_file).read_text(encoding="utf-8")
        (folder / "legendas.srt").write_text(srt_text, encoding="utf-8")

        cue_count = len([line for line in srt_text.splitlines() if re.fullmatch(r"\d+", line.strip())])
        result = {
            "srt_file": "legendas.srt", "srt_mode": chosen, "cue_count": cue_count,
            "word_count": len(words), "duration": round(duration, 3),
            "script_ratio": round(script_ratio, 3), "cached": bool(transcript.get("cached")),
        }
        update_job(
            job_id, status="complete", stage="ready", progress=100, completed=1, total=1,
            message=f"Transcrição concluída: {len(words)} palavras e {cue_count} blocos de legenda.",
            word_count=len(words), duration=round(duration, 3), script_ratio=round(script_ratio, 3),
            script_srt=bool(script_srt), srt_mode=chosen, cue_count=cue_count,
            cached=bool(transcript.get("cached")), result=result,
            text=str(transcript.get("text") or "")[:6000],
        )
        _apply_to_project(job_id, state, folder / chosen_file)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else f"Erro interno: {type(exc).__name__}: {exc}"
        try:
            key = groq_key()
            if key:
                message = message.replace(key, "***")
        except Exception:
            pass
        try:
            update_job(job_id, status="failed", stage="error", error=message[:500],
                       message=message[:500], finished_at=now_iso())
        except Exception:
            pass
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _apply_to_project(job_id: str, state: dict[str, Any], srt_path: Path) -> None:
    project_id = state.get("project_id")
    if not project_id:
        return
    try:
        current = read_job(job_id)
        project = read_state(project_id)
        folder = project_dir(project_id)
        target_name = "subtitles_groq.srt"
        shutil.copy2(srt_path, folder / target_name)
        srt_text = (folder / target_name).read_text(encoding="utf-8-sig", errors="replace")
        cue_count = len([line for line in srt_text.splitlines() if re.fullmatch(r"\d+", line.strip())])

        def apply(s: dict[str, Any]) -> None:
            s["srt_file"] = target_name
            s["cue_count"] = cue_count
            s["srt_source"] = "groq"
            s["srt_updated_at"] = now_iso()
            s["groq"] = {
                "job_id": job_id, "model": current.get("model"), "language": current.get("language"),
                "word_count": current.get("word_count") or 0, "script_ratio": current.get("script_ratio") or 0,
                "updated_at": now_iso(),
            }
            log = s.setdefault("log", [])
            seq = int(s.get("log_seq", 0)) + 1
            log.append({"n": seq, "t": now_iso(), "stage": "parse", "level": "info",
                        "msg": f"Legendas atualizadas com Groq: {cue_count} blocos sincronizados por palavra."})
            s["log_seq"] = seq
            s["scenes_rev"] = int(s.get("scenes_rev", 0)) + 1

        patch_state(project_id, apply)
        update_job(job_id, applied_to_project=project_id)
    except Exception as exc:
        try:
            update_job(job_id, project_warning=f"Não foi possível aplicar no projeto: {str(exc)[:200]}")
        except Exception:
            pass


# ------------------------------------------------------------------ orientação de uso

def guidance() -> dict[str, Any]:
    """Texto estruturado que a interface usa para explicar quando usar o Groq."""
    return {
        "always_ok": True,
        "recommended_model": DEFAULT_MODEL,
        "when": [
            "O SRT veio estimado (por exemplo, gerado pelo Fish Audio) e as legendas precisam casar com a voz.",
            "Você vai usar legendas palavra a palavra, Shorts ou CapCut e precisa de tempos exatos.",
            "O roteiro original precisa ser mantido, mas sincronizado com a narração real.",
            "O vídeo tem silêncios, pausas ou fala irregular que quebram a estimativa por duração.",
            "Você quer conferir se o áudio corresponde ao roteiro antes de montar.",
        ],
        "always_note": (
            "Pode ser usado em todos os projetos. O áudio acima de 24 MB é comprimido e dividido "
            "automaticamente. Cada minuto consome cota da Groq; a mesma narração é cacheada e não "
            "é cobrada duas vezes."
        ),
        "limits": {
            "api_mb": round(API_LIMIT / 1024 / 1024, 1),
            "upload_mb": round(MAX_UPLOAD / 1024 / 1024, 1),
            "max_active": MAX_ACTIVE_JOBS,
            "models": [m["id"] for m in MODELS],
        },
    }
