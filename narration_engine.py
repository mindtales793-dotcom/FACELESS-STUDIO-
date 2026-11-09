"""Motor otimizado de narração com Fish Audio.

Recursos implementados:
- Geração inteligente em blocos (não corta frases, agrupa curtas)
- Processamento paralelo com concorrência controlada
- Cache inteligente por texto + voz + configurações
- Montagem com FFmpeg (normalização, pausas naturais)
- Controle de pausa/cancelamento
- Progresso detalhado por bloco
- Parâmetros de voz (velocidade, estabilidade, expressividade)
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException

from providers import provider_key
from store import DATA_DIR, ffmpeg_path, ffprobe_path, lock, now_iso

FISH_API_BASE = "https://api.fish.audio"

# ---------------------------------------------------------------------------
# Vozes salvas (preservadas da implementação original)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Utilitários de texto e cache
# ---------------------------------------------------------------------------

def _text_fingerprint(text: str, reference_id: str | None, model: str,
                      speed: float, stability: float, expressiveness: float) -> str:
    """Gera um hash único para identificar um bloco de narração."""
    payload = f"{text}|{reference_id or ''}|{model}|{speed}|{stability}|{expressiveness}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def split_text_chunks_intelligent(text: str, max_chars: int = 2200,
                                  min_chars: int = 600) -> list[str]:
    """Divide o roteiro em blocos inteligentes.

    Regras:
    - Nunca corta uma frase no meio.
    - Agrupa frases curtas até atingir min_chars.
    - Limite suave de max_chars (pode exceder ligeiramente para não cortar frase).
    - Respeita pontuação (. ! ? …) como ponto de quebra.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("Digite um roteiro antes de gerar a narração.")

    # Divide em sentenças mantendo o delimitador
    sentences = re.split(r"([.!?…]+)", text)
    # Reconstroi sentenças com seus delimitadores
    rebuilt: list[str] = []
    i = 0
    while i < len(sentences):
        part = sentences[i].strip()
        if i + 1 < len(sentences) and sentences[i + 1] in (".", "!", "?", "…", ". ", "! ", "? ", "… "):
            part = (part + sentences[i + 1]).strip()
            i += 2
        else:
            i += 1
        if part:
            rebuilt.append(part)

    if not rebuilt:
        rebuilt = [text]

    chunks: list[str] = []
    current = ""

    for sentence in rebuilt:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Se a sentença sozinha excede max_chars, divide por palavras (último recurso)
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sentence.split()
            word_current = ""
            for word in words:
                if word_current and len(word_current) + len(word) + 1 > max_chars:
                    chunks.append(word_current)
                    word_current = word
                else:
                    word_current = f"{word_current} {word}".strip() if word_current else word
            if word_current:
                current = word_current
            continue

        if current and len(current) + len(sentence) + 1 > max_chars:
            # Se o current já tem pelo menos min_chars, fecha o chunk
            if len(current) >= min_chars:
                chunks.append(current)
                current = sentence
            else:
                # current muito curto, força adicionar mesmo excedendo levemente
                current = f"{current} {sentence}".strip()
        else:
            current = f"{current} {sentence}".strip() if current else sentence

    if current:
        chunks.append(current)

    return chunks


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_estimated_srt(chunks: list[str], durations: list[float]) -> str:
    """Cria SRT estimado baseado na duração de cada chunk."""
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


# ---------------------------------------------------------------------------
# Cache inteligente
# ---------------------------------------------------------------------------

class NarrationCache:
    """Gerencia cache de áudios já gerados."""

    def __init__(self, cache_dir: Path):
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.dir / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        if self.index_file.exists():
            try:
                self._index = json.loads(self.index_file.read_text(encoding="utf-8"))
            except Exception:
                self._index = {}

    def _save_index(self) -> None:
        with lock:
            self.index_file.write_text(json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, fingerprint: str) -> dict[str, Any] | None:
        """Retorna metadados do cache se o áudio existir."""
        entry = self._index.get(fingerprint)
        if not entry:
            return None
        audio_path = self.dir / entry["file"]
        if not audio_path.exists():
            return None
        return entry

    def put(self, fingerprint: str, file_name: str, duration: float,
            text: str, reference_id: str | None, model: str,
            speed: float, stability: float, expressiveness: float) -> None:
        self._index[fingerprint] = {
            "file": file_name,
            "duration": duration,
            "text": text,
            "reference_id": reference_id,
            "model": model,
            "speed": speed,
            "stability": stability,
            "expressiveness": expressiveness,
            "created_at": now_iso(),
        }
        self._save_index()

    def list_cached(self) -> list[dict[str, Any]]:
        return list(self._index.values())


# ---------------------------------------------------------------------------
# Geração individual de um bloco (com retry e cache)
# ---------------------------------------------------------------------------

def fish_tts_bytes(text: str, reference_id: str | None, model: str, api_key: str,
                   speed: float = 1.0, stability: float = 0.5,
                   expressiveness: float = 0.5, max_retries: int = 3) -> bytes:
    """Gera áudio via Fish Audio com parâmetros de voz e retry."""
    payload: dict[str, Any] = {
        "text": text,
        "format": "mp3",
        "speed": speed,
        "stability": stability,
        "expressiveness": expressiveness,
    }
    if reference_id:
        payload["reference_id"] = reference_id

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                f"{FISH_API_BASE}/v1/tts",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "model": model,
                },
                json=payload,
                timeout=(20, 180),
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
                sleep_time = 2 * (attempt + 1)
                time.sleep(sleep_time)
                continue
            raise last_error


# ---------------------------------------------------------------------------
# Motor principal de narração
# ---------------------------------------------------------------------------

class NarrationEngine:
    """Motor de narração com processamento paralelo, cache e controle de pausa."""

    def __init__(self):
        self.cache_dir = DATA_DIR / "narration_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = NarrationCache(self.cache_dir)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._executors: dict[str, ThreadPoolExecutor] = {}
        self._cancel_flags: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Gestão de jobs
    # ------------------------------------------------------------------
    def create_job(self, text: str, reference_id: str | None, model: str,
                   speed: float = 1.0, stability: float = 0.5,
                   expressiveness: float = 0.5, max_concurrent: int = 4) -> dict[str, Any]:
        """Cria um novo job de narração e retorna o estado inicial."""
        chunks = split_text_chunks_intelligent(text)
        job_id = uuid.uuid4().hex
        folder = DATA_DIR / "narrations" / job_id
        folder.mkdir(parents=True, exist_ok=True)

        # Pré-carrega blocos com status de cache
        block_infos: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            fp = _text_fingerprint(chunk, reference_id, model, speed, stability, expressiveness)
            cached = self.cache.get(fp)
            block_infos.append({
                "index": idx,
                "text": chunk,
                "fingerprint": fp,
                "cached": bool(cached),
                "status": "cached" if cached else "pending",
                "duration": cached.get("duration") if cached else None,
                "error": None,
            })

        state = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "Narração adicionada à fila do Fish Audio.",
            "model": model,
            "reference_id": reference_id,
            "chunks": chunks,
            "chunk_count": len(chunks),
            "blocks": block_infos,
            "cached_blocks": sum(1 for b in block_infos if b["cached"]),
            "pending_blocks": sum(1 for b in block_infos if not b["cached"]),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "error": None,
            "paused": False,
            "cancelled": False,
            "speed": speed,
            "stability": stability,
            "expressiveness": expressiveness,
            "max_concurrent": max_concurrent,
            "audio_file": None,
            "srt_file": None,
            "duration": None,
        }
        self._write_job(job_id, state)
        self._jobs[job_id] = state
        self._cancel_flags[job_id] = False
        return {"id": job_id, "status": "queued", "chunk_count": len(chunks),
                "cached_blocks": state["cached_blocks"],
                "pending_blocks": state["pending_blocks"]}

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Retorna o estado público do job."""
        state = self._read_job(job_id)
        public = {k: v for k, v in state.items()
                  if k not in ("chunks", "reference_id")}
        if state.get("status") == "complete":
            public["audio_url"] = f"/api/narrations/{job_id}/download"
            public["srt_url"] = f"/api/narrations/{job_id}/subtitles"
        public["paused"] = bool(state.get("paused"))
        public["cancelled"] = bool(state.get("cancelled"))
        return public

    def get_block_status(self, job_id: str) -> list[dict[str, Any]]:
        """Retorna o status detalhado de cada bloco."""
        state = self._read_job(job_id)
        return state.get("blocks", [])

    def pause(self, job_id: str) -> None:
        state = self._read_job(job_id)
        if state.get("status") not in ("queued", "generating"):
            raise HTTPException(status_code=409, detail="Só é possível pausar uma narração em andamento.")
        state["paused"] = True
        state["message"] = "Narração pausada pelo usuário."
        state["updated_at"] = now_iso()
        self._write_job(job_id, state)

    def resume(self, job_id: str, background_tasks: Any) -> None:
        state = self._read_job(job_id)
        if state.get("status") not in ("queued", "generating"):
            raise HTTPException(status_code=409, detail="Não há narração para retomar.")
        if not state.get("paused") and state.get("status") == "generating":
            return
        state["paused"] = False
        state["cancelled"] = False
        state["message"] = "Retomando narração…"
        state["updated_at"] = now_iso()
        self._write_job(job_id, state)
        self._cancel_flags[job_id] = False
        background_tasks.add_task(self._run_generation, job_id)

    def cancel(self, job_id: str) -> None:
        """Cancela a geração de narração."""
        state = self._read_job(job_id)
        if state.get("status") in ("complete", "failed"):
            raise HTTPException(status_code=409, detail="Não é possível cancelar uma narração já finalizada.")
        state["cancelled"] = True
        state["paused"] = False
        state["message"] = "Cancelamento solicitado…"
        state["updated_at"] = now_iso()
        self._write_job(job_id, state)
        self._cancel_flags[job_id] = True

    def redo(self, job_id: str, background_tasks: Any) -> None:
        state = self._read_job(job_id)
        folder = self._job_dir(job_id)
        for f in folder.glob("chunk_*.mp3"):
            f.unlink(missing_ok=True)
        for f in (folder / "narration.mp3", folder / "narration.srt", folder / "audio_parts.txt"):
            f.unlink(missing_ok=True)
        # Reseta blocos para pending (remove cache hit para forçar regeneração)
        for b in state.get("blocks", []):
            b["status"] = "pending"
            b["cached"] = False
            b["duration"] = None
            b["error"] = None
        state["status"] = "queued"
        state["progress"] = 0
        state["paused"] = False
        state["cancelled"] = False
        state["message"] = "Recomeçando a narração…"
        state["error"] = None
        state["updated_at"] = now_iso()
        state.pop("audio_file", None)
        state.pop("srt_file", None)
        state.pop("duration", None)
        state["cached_blocks"] = 0
        state["pending_blocks"] = len(state.get("blocks", []))
        self._write_job(job_id, state)
        self._cancel_flags[job_id] = False
        background_tasks.add_task(self._run_generation, job_id)

    # ------------------------------------------------------------------
    # Leitura/escrita de job
    # ------------------------------------------------------------------
    def _job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise HTTPException(status_code=404, detail="Geração de narração não encontrada.")
        folder = DATA_DIR / "narrations" / job_id
        if not folder.exists():
            raise HTTPException(status_code=404, detail="Geração de narração não encontrada.")
        return folder

    def _read_job(self, job_id: str) -> dict[str, Any]:
        folder = self._job_dir(job_id)
        try:
            return json.loads((folder / "job.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise HTTPException(status_code=500, detail="Não foi possível ler o status da narração.")

    def _write_job(self, job_id: str, data: dict[str, Any]) -> None:
        folder = DATA_DIR / "narrations" / job_id
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / "job.json.tmp"
        with lock:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(folder / "job.json")
        # Mantém cópia em memória para acesso rápido
        self._jobs[job_id] = data

    # ------------------------------------------------------------------
    # Geração principal (background task)
    # ------------------------------------------------------------------
    def _run_generation(self, job_id: str) -> None:
        """Executa a geração completa (chamado via background task)."""
        folder = self._job_dir(job_id)
        state = self._read_job(job_id)
        try:
            state["status"] = "generating"
            state["progress"] = 1
            state["message"] = "Validando conexão com o Fish Audio…"
            self._write_job(job_id, state)

            api_key = provider_key("FISH_API_KEY", "Fish Audio")
            chunks = state["chunks"]
            blocks = state.get("blocks", [])
            model = state["model"]
            reference_id = state.get("reference_id")
            speed = state.get("speed", 1.0)
            stability = state.get("stability", 0.5)
            expressiveness = state.get("expressiveness", 0.5)
            max_concurrent = state.get("max_concurrent", 4)
            ffmpeg = ffmpeg_path()
            ffprobe = ffprobe_path()

            # Teste rápido de conexão
            try:
                fish_tts_bytes("ok", reference_id, model, api_key,
                               speed, stability, expressiveness)
            except Exception as conn_exc:
                raise RuntimeError(
                    "Não foi possível conectar ao Fish Audio. Verifique sua "
                    f"chave FISH_API_KEY e a conexão com a internet. Detalhe: {conn_exc}"
                )

            # Filtra blocos que precisam ser gerados (não estão em cache)
            blocks_to_generate = [
                (i, b) for i, b in enumerate(blocks)
                if not b.get("cached") and b.get("status") != "complete"
            ]

            total_blocks = len(blocks)
            completed_blocks = sum(1 for b in blocks if b.get("status") == "complete")
            durations: list[float] = [0.0] * total_blocks
            files: list[Path] = [None] * total_blocks  # type: ignore

            # Preenche durações de blocos em cache
            for b in blocks:
                if b.get("cached") and b.get("duration") is not None:
                    idx = b["index"]
                    durations[idx] = b["duration"]

            # Processa em paralelo com concorrência controlada
            executor = ThreadPoolExecutor(max_workers=max_concurrent)
            self._executors[job_id] = executor

            futures: dict[Future, int] = {}
            for idx, b in blocks_to_generate:
                fp = b["fingerprint"]
                # Verifica cache novamente (pode ter sido gerado por outro processo)
                cached = self.cache.get(fp)
                if cached:
                    b["status"] = "complete"
                    b["cached"] = True
                    b["duration"] = cached.get("duration")
                    durations[idx] = cached.get("duration", 0.0)
                    completed_blocks += 1
                    continue

                future = executor.submit(
                    self._generate_single_block,
                    idx, b["text"], reference_id, model, api_key,
                    speed, stability, expressiveness, folder
                )
                futures[future] = idx

            # Acompanha conclusão dos blocos
            for future in as_completed(futures):
                if self._cancel_flags.get(job_id):
                    executor.shutdown(wait=False, cancel_futures=True)
                    state["status"] = "failed"
                    state["message"] = "Narração cancelada pelo usuário."
                    state["error"] = "Cancelado pelo usuário"
                    state["updated_at"] = now_iso()
                    self._write_job(job_id, state)
                    return

                # Respeita pausa
                state = self._read_job(job_id)
                while state.get("paused"):
                    if state.get("status") in ("failed", "complete") or state.get("cancelled"):
                        executor.shutdown(wait=False, cancel_futures=True)
                        return
                    time.sleep(1)
                    state = self._read_job(job_id)

                idx = futures[future]
                try:
                    audio_bytes, duration = future.result()
                    chunk_file = folder / f"chunk_{idx:03d}.mp3"
                    chunk_file.write_bytes(audio_bytes)
                    durations[idx] = max(0.25, duration)
                    files[idx] = chunk_file

                    # Atualiza bloco
                    b = blocks[idx]
                    b["status"] = "complete"
                    b["duration"] = durations[idx]
                    b["cached"] = False
                    b["error"] = None

                    # Salva no cache
                    fp = b["fingerprint"]
                    self.cache.put(fp, chunk_file.name, durations[idx],
                                   b["text"], reference_id, model,
                                   speed, stability, expressiveness)

                    completed_blocks += 1
                    progress = int(80 * completed_blocks / total_blocks) if total_blocks else 100
                    state["progress"] = progress
                    state["message"] = f"Gerando narração: {completed_blocks} de {total_blocks} blocos"
                    state["updated_at"] = now_iso()
                    self._write_job(job_id, state)
                except Exception as exc:
                    b = blocks[idx]
                    b["status"] = "failed"
                    b["error"] = str(exc)
                    raise RuntimeError(f"Falha ao gerar bloco {idx + 1}: {exc}")

            executor.shutdown(wait=True)
            self._executors.pop(job_id, None)

            if self._cancel_flags.get(job_id):
                state["status"] = "failed"
                state["message"] = "Narração cancelada pelo usuário."
                state["error"] = "Cancelado pelo usuário"
                state["updated_at"] = now_iso()
                self._write_job(job_id, state)
                return

            # Montagem final com FFmpeg
            state["message"] = "Juntando áudios com FFmpeg…"
            state["updated_at"] = now_iso()
            self._write_job(job_id, state)

            output = folder / "narration.mp3"
            self._merge_audio(files, durations, output, ffmpeg)

            # SRT
            srt_text = build_estimated_srt(chunks, durations)
            (folder / "narration.srt").write_text(srt_text, encoding="utf-8")

            # Limpa chunks individuais
            for f in files:
                if f and f.exists():
                    f.unlink(missing_ok=True)

            state.update({
                "status": "complete",
                "progress": 100,
                "message": "Narração pronta. As legendas geradas têm tempos estimados.",
                "audio_file": output.name,
                "srt_file": "narration.srt",
                "duration": round(sum(durations), 2),
                "updated_at": now_iso(),
            })
            state.pop("chunks", None)
            state.pop("reference_id", None)
            self._write_job(job_id, state)

        except Exception as exc:
            # Limpa chunks parciais em caso de falha
            try:
                for part in folder.glob("chunk_*.mp3"):
                    part.unlink(missing_ok=True)
            except Exception:
                pass
            state = self._read_job(job_id)
            state.update({
                "status": "failed",
                "progress": 100,
                "message": str(exc),
                "error": str(exc),
                "updated_at": now_iso(),
            })
            state.pop("chunks", None)
            state.pop("reference_id", None)
            self._write_job(job_id, state)

    def _generate_single_block(self, index: int, text: str, reference_id: str | None,
                               model: str, api_key: str, speed: float,
                               stability: float, expressiveness: float,
                               folder: Path) -> tuple[bytes, float]:
        """Gera um único bloco de áudio. Retorna (bytes, duração_segundos)."""
        audio_bytes = fish_tts_bytes(text, reference_id, model, api_key,
                                     speed, stability, expressiveness)
        chunk_file = folder / f"chunk_{index:03d}.mp3"
        chunk_file.write_bytes(audio_bytes)

        # Mede duração com ffprobe
        ffprobe = ffprobe_path()
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(chunk_file)],
            capture_output=True, text=True, timeout=45,
        )
        if probe.returncode != 0:
            raise RuntimeError("Não foi possível ler a duração do trecho gerado.")
        duration = max(0.25, float(probe.stdout.strip()))
        return audio_bytes, duration

    def _merge_audio(self, files: list[Path], durations: list[float],
                     output: Path, ffmpeg: str) -> None:
        """Une todos os áudios com FFmpeg, adicionando pausas naturais."""
        # Cria um arquivo de silêncio de 0.3s para pausas entre blocos.
        # (antes usava anoisesrc com c=mono: opção inválida, o FFmpeg falhava em silêncio
        # e nenhuma pausa era inserida; e anoisesrc geraria ruído, não silêncio.)
        pause_file = output.parent / "pause_03s.mp3"
        pause = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "0.3", "-c:a", "libmp3lame", "-b:a", "128k", str(pause_file)],
            capture_output=True, text=True, timeout=60,
        )
        if pause.returncode != 0:
            pause_file.unlink(missing_ok=True)  # segue sem pausas em vez de quebrar a narração

        all_files: list[Path] = []
        for i, f in enumerate(files):
            if f is None or not f.exists():
                continue
            all_files.append(f)
            if i < len(files) - 1 and pause_file and pause_file.exists():
                all_files.append(pause_file)

        concat_file = output.parent / "audio_parts.txt"
        with concat_file.open("w", encoding="utf-8") as cf:
            for f in all_files:
                cf.write(f"file '{f.name}'\n")

        merge = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c:a", "libmp3lame", "-b:a", "192k", "-af", "loudnorm", str(output)],
            capture_output=True, text=True, timeout=max(600, sum(durations) * 8),
        )
        if merge.returncode != 0:
            raise RuntimeError(f"Falha ao juntar os trechos de áudio: {(merge.stderr or merge.stdout)[-1600:]}")

        # Limpeza
        concat_file.unlink(missing_ok=True)
        if pause_file and pause_file.exists():
            pause_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def get_audio_file(self, job_id: str) -> Path:
        state = self._read_job(job_id)
        if state.get("status") != "complete":
            raise HTTPException(status_code=409, detail="A narração ainda não está pronta.")
        return self._job_dir(job_id) / state.get("audio_file", "narration.mp3")

    def get_srt_file(self, job_id: str) -> Path:
        state = self._read_job(job_id)
        if state.get("status") != "complete":
            raise HTTPException(status_code=409, detail="As legendas ainda não estão prontas.")
        return self._job_dir(job_id) / state.get("srt_file", "narration.srt")


# Instância global do motor
narration_engine = NarrationEngine()

# Mantém compatibilidade com funções antigas usadas pelo main.py
nar = narration_engine


# Funções de nível de módulo para compatibilidade com main.py
def create_job(text: str, reference_id: str | None, model: str,
               speed: float = 1.0, stability: float = 0.5,
               expressiveness: float = 0.5, max_concurrent: int = 4) -> dict[str, Any]:
    return narration_engine.create_job(
        text=text, reference_id=reference_id, model=model,
        speed=speed, stability=stability,
        expressiveness=expressiveness, max_concurrent=max_concurrent
    )


def get_job(job_id: str) -> dict[str, Any]:
    return narration_engine.get_job(job_id)


def get_block_status(job_id: str) -> list[dict[str, Any]]:
    return narration_engine.get_block_status(job_id)


def pause(job_id: str) -> None:
    narration_engine.pause(job_id)


def resume(job_id: str, background_tasks: Any) -> None:
    narration_engine.resume(job_id, background_tasks)


def cancel(job_id: str) -> None:
    narration_engine.cancel(job_id)


def redo(job_id: str, background_tasks: Any) -> None:
    narration_engine.redo(job_id, background_tasks)


def get_audio_file(job_id: str) -> Path:
    return narration_engine.get_audio_file(job_id)


def get_srt_file(job_id: str) -> Path:
    return narration_engine.get_srt_file(job_id)


def _run_generation(job_id: str) -> None:
    narration_engine._run_generation(job_id)


def _read_job(job_id: str) -> dict[str, Any]:
    return narration_engine._read_job(job_id)


def _write_job(job_id: str, data: dict[str, Any]) -> None:
    narration_engine._write_job(job_id, data)


def _job_dir(job_id: str) -> Path:
    return narration_engine._job_dir(job_id)


def split_text_chunks(text: str, max_chars: int = 4000) -> list[str]:
    """Compatibilidade com a API antiga."""
    return split_text_chunks_intelligent(text, max_chars=max_chars)


def fish_voice_models(api_key: str) -> list[dict[str, str]]:
    """Lista vozes da conta Fish Audio (compatibilidade)."""
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
