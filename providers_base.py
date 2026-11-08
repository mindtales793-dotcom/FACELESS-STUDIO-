"""Interfaces abstratas de provedores externos.

Toda chamada externa fica atrás destas interfaces para poder trocar o serviço
sem mexer no pipeline. Implementações concretas herdam e preenchem os métodos.
Nenhuma chave de API é logada.
"""
from __future__ import annotations

import os
from typing import Any


class MediaProvider:
    """Busca mídia (imagem/vídeo/áudio) nos bancos externos.

    Devolve lista de candidatos com metadados de licença para os créditos.
    """

    name: str = "base"
    needs_key: bool = False
    env_key: str | None = None

    def is_ready(self) -> bool:
        if self.needs_key:
            return bool(os.getenv(self.env_key or "", "").strip())
        return True  # provedor sem chave está sempre disponível

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        """Busca mídia. Devolve [{provider, id, url_origem, thumbnail, duration,
        width, height, license, author, photographer, requires_attribution, ...}]."""
        raise NotImplementedError

    def public_meta(self) -> dict[str, Any]:
        return {"id": self.name, "needs_key": self.needs_key, "ready": self.is_ready()}


class ImageGenProvider:
    """Geração de imagem (Nano Banana, GPT Image, etc.)."""

    name: str = "base"
    needs_key: bool = False
    env_key: str | None = None

    def is_ready(self) -> bool:
        if self.needs_key:
            return bool(os.getenv(self.env_key or "", "").strip())
        return True

    async def generate(self, prompt: str, ratio: str = "16:9",
                       reference_images: list[str] | None = None,
                       **kwargs: Any) -> dict[str, Any]:
        """Gera uma imagem. Devolve {url, path, prompt, model, size_mb, ...}."""
        raise NotImplementedError


class VideoGenProvider:
    """Geração de vídeo (Veo, Gemini Omni, etc.)."""

    name: str = "base"
    needs_key: bool = False
    env_key: str | None = None

    def is_ready(self) -> bool:
        if self.needs_key:
            return bool(os.getenv(self.env_key or "", "").strip())
        return True

    async def generate(self, prompt: str, ratio: str = "16:9", seconds: int = 6,
                       reference_image: str | None = None,
                       **kwargs: Any) -> dict[str, Any]:
        """Gera um clipe de vídeo. Devolve {url, path, prompt, model, seconds, ...}."""
        raise NotImplementedError


class AvatarProvider:
    """Geração de avatar falante (HeyGen, etc.)."""

    name: str = "base"
    needs_key: bool = False
    env_key: str | None = None

    def is_ready(self) -> bool:
        if self.needs_key:
            return bool(os.getenv(self.env_key or "", "").strip())
        return True

    async def list_avatars(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def generate(self, avatar_id: str, audio_path: str | None = None,
                       text: str | None = None, background: str = "default",
                       **kwargs: Any) -> dict[str, Any]:
        """Gera vídeo do avatar. Devolve {url, path, status, ...}."""
        raise NotImplementedError

    async def list_avatars(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def generate(self, avatar_id: str, audio_path: str | None = None,
                       text: str | None = None, background: str = "default",
                       **kwargs: Any) -> dict[str, Any]:
        """Gera vídeo do avatar. Devolve {url, path, status, ...}."""
        raise NotImplementedError


class MediaFetcher:
    """Aquisição de arquivo de mídia (ex.: download de clipe do YouTube).

    Implementação concreta é decisão do dono do projeto — não contornamos
    proteções nem termos de uso. Registro em docs/decisoes.md.
    """

    name: str = "base"

    async def fetch(self, url: str, dest_dir: str | None = None) -> dict[str, Any]:
        """Baixa o arquivo. Devolve {path, filename, size_mb, duration, ...}."""
        raise NotImplementedError
