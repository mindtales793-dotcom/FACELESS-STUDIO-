"""Narração com Fish Audio: divide o roteiro, gera o MP3 no servidor e cria um SRT estimado."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException

from providers import provider_key
from store import DATA_DIR, ffmpeg_path, ffprobe_path, lock, now_iso

FISH_API_BASE = "https://api.fish.audio"

SAVED_VOICES: list[dict[str, Any]] = [
    {
        "id": "bf322df2096a46f18c579d0baa36f41d",
        "title": "Adrian",
        "description": "Voz masculina estável, firme e confiável. Ideal para narrações cinematográficas e documentários.",
        "lang": "en",
        "lang_label": "Inglês",
        "flag": "🇺🇸",
        "tags": ["Firme", "Confiável", "Documentário"],
    },
    {
        "id": "536d3a5e000945adb7038665781a4aca",
        "title": "Ethan",
        "description": "Tom curioso e explicativo. Excelente para vídeos didáticos, curiosidades e canais explainer.",
        "lang": "en",
        "lang_label": "Inglês",
        "flag": "🇺🇸",
        "tags": ["Curioso", "Didático", "Explainer"],
    },
    {
        "id": "f8dfe9c83081432386f143e2fe9767ef",
        "title": "Book Record Regular",
        "description": "Voz masculina madura, profunda, rasgada e rouca com autoridade para contação dramática de histórias.",
        "lang": "en",
        "lang_label": "Inglês",
        "flag": "🇺🇸",
        "tags": ["Grave", "Rouca", "Storytelling"],
    },
    {
        "id": "bf4a01bacf1b43b188c2c13ebdc77166",
        "title": "Marcus - Calm Male Narrator",
        "description": "Narrador masculino calmo e claro para YouTube Faceless, documentários e podcasts. Dicção quente e natural.",
        "lang": "en",
        "lang_label": "Inglês",
        "flag": "🇺🇸",
        "tags": ["Calmo", "YouTube", "Faceless"],
    },
    {
        "id": "a754ca8729d642d9a918a42b5b6a77d1",
        "title": "Dave - Australian Male",
        "description": "Voz masculina profunda com sotaque australiano natural. Ótima para redes sociais e narração moderna.",
        "lang": "en",
        "lang_label": "Inglês (AU)",
        "flag": "🇦🇺",
        "tags": ["Profunda", "Australiano", "Social Media"],
    },
    {
        "id": "53ac6dc4ad314fed88aa28732ad9c87d",
        "title": "Gabriel VO - Spanish Narrator",
        "description": "Voz castelhana profunda e ressonante com presença calorosa. Perfeita para documentários e thrillers.",
        "lang": "es",
        "lang_label": "Espanhol",
        "flag": "🇪🇸",
        "tags": ["Castelhano", "Profundo", "Documentário"],
    },
    {
        "id": "d219d7c37aeb4fba87b4567ef982ce86",
        "title": "Rui Burigo",
        "description": "Voz masculina suave e tranquila em português. Transmite paz, bem-estar, autenticidade e conexão.",
        "lang": "pt",
        "lang_label": "Português",
        "flag": "🇧🇷",
        "tags": ["Suave", "Tranquila", "Autêntica"],
    },
    {
        "id": "6fdff31635694522b2bb6592c49f02e8",
        "title": "Melky Fernandes",
        "description": "Voz calma e pensativa em português. Ideal para reflexão e observação do cotidiano com clareza e serenidade.",
        "lang": "pt",
        "lang_label": "Português",
        "flag": "🇧🇷",
        "tags": ["Calma", "Reflexiva", "Serena"],
    },
    {
        "id": "195885c4f0994bebb1160a6a500fa63d",
        "title": "Narrativa Serena e Calma",
        "description": "Voz masculina suave e introspectiva em português. Excelente para conteúdos de reflexão, meditação e paz.",
        "lang": "pt",
        "lang_label": "Português",
        "flag": "🇧🇷",
        "tags": ["Serena", "Introspectiva", "Paz"],
    },
    {
        "id": "ecf9605f63d04284bbb36a9bb2d53966",
        "title": "João M (Narrativa Calma)",
        "description": "Voz masculina calma e reflexiva em português. Dicção pausada e clara para momentos de introspecção.",
        "lang": "pt",
        "lang_label": "Português",
        "flag": "🇧🇷",
        "tags": ["Calma", "Pausada", "Introspecção"],
    },
]


def saved_fish_voices() -> list[dict[str, Any]]:
    return SAVED_VOICES


def split_text_chunks(text: str, max_chars: int = 4000) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("Digite um roteiro antes de gerar a narração.")
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            words = sentence.split()
            for word in words:
                if current and len(current) + len(word) + 1 > max_chars:
                    chunks.append(current)
                    current = ""
                current = f"{current} {word}".strip()
            continue
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def fish_tts_bytes(text: str, reference_id: str | None, model: str, api_key: str, max_retries: int = 2) -> bytes:
    payload: dict[str, Any] = {"text": text, "format": "mp3"}
    if reference_id:
        payload["reference_id"] = reference_id
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                f"{FISH_API_BASE}/v1/tts",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "model": model},
                json=payload, timeout=(20, 120),
            )
            if not response.ok:
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text[:500]
                raise RuntimeError(f"Fish Audio retornou {response.status_code}: {detail}")
            if not response.content:
                raise RuntimeError("Fish Audio retornou um arquivo de áudio vazio.")
            return response.content
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(2)
                continue
            raise last_error


def fish_voice_models(api_key: str) -> list[dict[str, str]]:
    response = requests.get(
        f"{FISH_API_BASE}/model",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"page_size": 100, "page_number": 1, "self": "true"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", payload.get("data", [])) if isinstance(payload, dict) else payload
    results = []
    for item in items or []:
        voice_id = item.get("_id") or item.get("id")
        if voice_id:
            results.append({"id": str(voice_id), "title": str(item.get("title") or item.get("name") or "Voz Fish Audio"), "state": str(item.get("state") or "")})
    return results


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_estimated_srt(chunks: list[str], durations: list[float]) -> str:
    """Create practical scene/subtitle cues estimated per generated chunk; not phoneme-aligned."""
    cues: list[tuple[float, float, str]] = []
    global_offset = 0.0
    for chunk, duration in zip(chunks, durations):
        sentences = re.split(r"(?<=[.!?…])\s+", chunk)
        cue_texts: list[str] = []
        for sentence in sentences:
            words = sentence.split()
            for i in range(0, len(words), 14):
                piece = " ".join(words[i:i + 14]).strip()
                if piece:
                    cue_texts.append(piece)
        if not cue_texts:
            global_offset += duration
            continue
        weights = [max(1, len(t.split())) * (1.12 if t.rstrip().endswith(('.', '!', '?', '…')) else 1.0) for t in cue_texts]
        total_weight = sum(weights) or 1
        cursor = global_offset
        for cue_text, weight in zip(cue_texts, weights):
            span = duration * weight / total_weight
            cues.append((cursor, cursor + span, cue_text))
            cursor += span
        global_offset += duration
    blocks = []
    for idx, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{idx}\n{srt_timestamp(start)} --> {srt_timestamp(max(start + 0.35, end))}\n{text}")
    return "\n\n".join(blocks) + "\n"


def narration_job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=404, detail="Geração de narração não encontrada.")
    folder = DATA_DIR / "narrations" / job_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Geração de narração não encontrada.")
    return folder


def read_narration_job(job_id: str) -> dict[str, Any]:
    folder = narration_job_dir(job_id)
    try:
        return json.loads((folder / "job.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Não foi possível ler o status da narração.")


def write_narration_job(job_id: str, data: dict[str, Any]) -> None:
    folder = DATA_DIR / "narrations" / job_id
    temp = folder / "job.json.tmp"
    with lock:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(folder / "job.json")


def generate_narration_job(job_id: str) -> None:
    folder = narration_job_dir(job_id)
    state = read_narration_job(job_id)
    try:
        state["status"] = "generating"
        state["progress"] = 1
        state["message"] = "Validando conexão com o Fish Audio…"
        write_narration_job(job_id, state)
        api_key = provider_key("FISH_API_KEY", "Fish Audio")
        chunks = state["chunks"]
        durations: list[float] = []
        ffmpeg = ffmpeg_path()
        ffprobe = ffprobe_path()
        files = []

        # Teste rápido de conexão antes de iniciar: gera um trecho ínfimo para
        # falhar imediatamente se a rede/chave estiver fora, em vez de travar
        # no primeiro trecho do roteiro real.
        try:
            fish_tts_bytes("ok", state.get("reference_id"), state["model"], api_key)
        except Exception as conn_exc:
            raise RuntimeError(
                "Não foi possível conectar ao Fish Audio. Verifique sua "
                f"chave FISH_API_KEY e a conexão com a internet. Detalhe: {conn_exc}"
            )
        for index, chunk in enumerate(chunks, 1):
            # respeita pausa entre trechos: aguarda até ser retomado
            state = read_narration_job(job_id)
            while state.get("paused"):
                if state.get("status") in ("failed", "complete"):
                    return
                time.sleep(1)
                state = read_narration_job(job_id)
            audio_bytes = fish_tts_bytes(chunk, state.get("reference_id"), state["model"], api_key)
            chunk_file = folder / f"chunk_{index:03d}.mp3"
            chunk_file.write_bytes(audio_bytes)
            probe = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(chunk_file)],
                capture_output=True, text=True, timeout=45,
            )
            if probe.returncode != 0:
                raise RuntimeError("Não foi possível ler a duração de um trecho gerado pelo Fish Audio.")
            durations.append(max(0.25, float(probe.stdout.strip())))
            files.append(chunk_file)
            state["progress"] = int(80 * index / len(chunks))
            state["message"] = f"Gerando narração: trecho {index} de {len(chunks)}"
            write_narration_job(job_id, state)

        concat_file = folder / "audio_parts.txt"
        concat_file.write_text("\n".join(f"file '{f.name}'" for f in files), encoding="utf-8")
        output = folder / "narration.mp3"
        merge = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "libmp3lame", "-b:a", "192k", str(output)],
            capture_output=True, text=True, timeout=max(600, sum(durations) * 8),
        )
        if merge.returncode != 0:
            raise RuntimeError(f"Falha ao juntar os trechos de áudio: {(merge.stderr or merge.stdout)[-1600:]}")
        srt_text = build_estimated_srt(chunks, durations)
        (folder / "narration.srt").write_text(srt_text, encoding="utf-8")
        for chunk_file in files:
            chunk_file.unlink(missing_ok=True)
        concat_file.unlink(missing_ok=True)
        state.update({"status": "complete", "progress": 100, "message": "Narração pronta. As legendas geradas têm tempos estimados.", "audio_file": output.name, "srt_file": "narration.srt", "duration": round(sum(durations), 2), "updated_at": now_iso()})
        state.pop("chunks", None)
        state.pop("reference_id", None)
        write_narration_job(job_id, state)
    except Exception as exc:
        for part in folder.glob("chunk_*.mp3"):
            part.unlink(missing_ok=True)
        state.pop("chunks", None)
        state.pop("reference_id", None)
        state.update({"status": "failed", "progress": 100, "message": str(exc), "error": str(exc), "updated_at": now_iso()})
        write_narration_job(job_id, state)
