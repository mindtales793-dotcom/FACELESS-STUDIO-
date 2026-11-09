"""Cenas geradas por IA — Nano Banana 2.1, GPT Image, Gemini Omni.

Modelos vêm de configuração (variáveis de ambiente), nunca fixos no código.
Toda chamada fica atrás de ImageGenProvider / VideoGenProvider.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

from providers_base import ImageGenProvider, VideoGenProvider

API = "https://generativelanguage.googleapis.com/v1beta"

NANO_BANANA_MODEL = os.getenv("NANO_BANANA_MODEL", "gemini-2.5-flash-image")
GPT_IMAGE_MODEL = os.getenv("GPT_IMAGE_MODEL", "gpt-image-2")
GEMINI_VIDEO_MODEL = os.getenv("GEMINI_VIDEO_MODEL", "gemini-omni-1.2-flash")


class NanoBananaProvider(ImageGenProvider):
    name = "nano_banana"
    needs_key = True
    env_key = "GEMINI_API_KEY"

    async def generate(self, prompt: str, ratio: str = "16:9",
                       reference_images: list[str] | None = None,
                       **kwargs: Any) -> dict[str, Any]:
        import base64 as _b64
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY não configurada.")
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for ref in (reference_images or [])[:14]:
            try:
                data = open(ref, "rb").read()
                ext = ref.lower().rsplit(".", 1)[-1]
                mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
                parts.insert(0, {"inlineData": {"mimeType": mime, "data": _b64.b64encode(data).decode()}})
            except Exception:
                pass
        corpo = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": ratio if ratio in ("16:9", "9:16", "1:1") else "16:9"},
            },
        }
        resp = requests.post(f"{API}/models/{NANO_BANANA_MODEL}:generateContent",
                             headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                             json=corpo, timeout=(20, 180))
        if not resp.ok:
            raise RuntimeError(f"Nano Banana erro {resp.status_code}: {resp.text[:300]}")
        dados = resp.json()
        for cand in dados.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    from pathlib import Path
                    dest = Path("data/flow_gallery") / f"nano_{os.urandom(4).hex()}.png"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(_b64.b64decode(inline["data"]))
                    return {
                        "url": f"/api/flow/gallery/{dest.name}",
                        "path": str(dest),
                        "prompt": prompt,
                        "model": NANO_BANANA_MODEL,
                        "size_mb": round(dest.stat().st_size / (1024 * 1024), 2),
                    }
        raise RuntimeError("Nano Banana não devolveu imagem.")

    def public_meta(self) -> dict[str, Any]:
        return {"id": self.name, "needs_key": self.needs_key, "ready": self.is_ready()}


class GPTImageProvider(ImageGenProvider):
    name = "gpt_image"
    needs_key = True
    env_key = "OPENAI_API_KEY"

    async def generate(self, prompt: str, ratio: str = "16:9",
                       reference_images: list[str] | None = None,
                       **kwargs: Any) -> dict[str, Any]:
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY não configurada.")
        tamanho = {"16:9": "1536x1024", "9:16": "1024x1536", "1:1": "1024x1024"}.get(ratio, "1536x1024")
        corpo = {
            "model": GPT_IMAGE_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": tamanho,
        }
        if reference_images:
            corpo["image"] = reference_images[0]  # primeira referência para edição
        resp = requests.post("https://api.openai.com/v1/images/generations",
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                             json=corpo, timeout=(20, 180))
        if not resp.ok:
            raise RuntimeError(f"GPT Image erro {resp.status_code}: {resp.text[:300]}")
        dados = resp.json()
        url_img = dados["data"][0]["url"]
        # Baixa a imagem
        img_resp = requests.get(url_img, timeout=(20, 180))
        if not img_resp.ok:
            raise RuntimeError("Não consegui baixar a imagem gerada pelo GPT Image.")
        from pathlib import Path
        dest = Path("data/flow_gallery") / f"gpt_{os.urandom(4).hex()}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img_resp.content)
        return {
            "url": f"/api/flow/gallery/{dest.name}",
            "path": str(dest),
            "prompt": prompt,
            "model": GPT_IMAGE_MODEL,
            "size_mb": round(dest.stat().st_size / (1024 * 1024), 2),
        }

    def public_meta(self) -> dict[str, Any]:
        return {"id": self.name, "needs_key": self.needs_key, "ready": self.is_ready()}


class GeminiVideoProvider(VideoGenProvider):
    name = "gemini_video"
    needs_key = True
    env_key = "GEMINI_API_KEY"

    async def generate(self, prompt: str, ratio: str = "16:9", seconds: int = 6,
                       reference_image: str | None = None,
                       **kwargs: Any) -> dict[str, Any]:
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY não configurada.")
        # Usa a Interactions API para vídeo (Gemini Omni)
        corpo = {
            "model": GEMINI_VIDEO_MODEL,
            "prompt": prompt,
            "aspectRatio": ratio if ratio in ("16:9", "9:16", "1:1") else "16:9",
            "durationSeconds": max(3, min(15, seconds)),
        }
        if reference_image:
            try:
                import base64 as _b64
                data = open(reference_image, "rb").read()
                corpo["referenceImage"] = {"inlineData": {"mimeType": "image/png", "data": _b64.b64encode(data).decode()}}
            except Exception:
                pass
        resp = requests.post(f"{API}/interactions",
                             headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                             json=corpo, timeout=(20, 900))
        if not resp.ok:
            raise RuntimeError(f"Gemini Video erro {resp.status_code}: {resp.text[:300]}")
        dados = resp.json()
        # Tenta extrair URL do vídeo da resposta
        video_uri = ""
        try:
            samples = dados.get("generatedSamples") or dados.get("videos") or []
            video_uri = (samples[0].get("video") or samples[0]) if samples else {}
            if isinstance(video_uri, dict):
                video_uri = video_uri.get("uri", "")
        except Exception:
            pass
        if not video_uri:
            video_uri = dados.get("videoUri", "")
        # Baixa o vídeo
        from pathlib import Path
        dest = Path("data/flow_gallery") / f"video_{os.urandom(4).hex()}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if video_uri:
            dl = requests.get(video_uri, headers={"x-goog-api-key": key}, stream=True, timeout=(20, 300))
            if not dl.ok:
                raise RuntimeError("Não consegui baixar o vídeo gerado.")
            with dest.open("wb") as f:
                for chunk in dl.iter_content(1024 * 1024):
                    f.write(chunk)
        else:
            # Se não há URI direto, grava metadata para o usuário baixar manualmente
            dest.write_text(json.dumps({"prompt": prompt, "model": GEMINI_VIDEO_MODEL, "response": dados}, ensure_ascii=False), encoding="utf-8")
        return {
            "url": f"/api/flow/gallery/{dest.name}",
            "path": str(dest),
            "prompt": prompt,
            "model": GEMINI_VIDEO_MODEL,
            "seconds": max(3, min(15, seconds)),
            "size_mb": round(dest.stat().st_size / (1024 * 1024), 2),
        }

    def public_meta(self) -> dict[str, Any]:
        return {"id": self.name, "needs_key": self.needs_key, "ready": self.is_ready()}


# Registro de provedores de IA
IMAGE_GEN_PROVIDERS: list[ImageGenProvider] = [NanoBananaProvider(), GPTImageProvider()]
VIDEO_GEN_PROVIDERS: list[VideoGenProvider] = [GeminiVideoProvider()]


def get_image_gen(name: str) -> ImageGenProvider | None:
    for p in IMAGE_GEN_PROVIDERS:
        if p.name == name:
            return p
    return None


def get_video_gen(name: str) -> VideoGenProvider | None:
    for p in VIDEO_GEN_PROVIDERS:
        if p.name == name:
            return p
    return None
