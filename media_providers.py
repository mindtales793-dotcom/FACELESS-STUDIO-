"""Provedores de mídia (filmagem real) — cadeia de prioridade por cena.

Cada provedor herda de MediaProvider (providers_base.py) e devolve candidatos com
metadados de licença para os créditos. Nenhuma chave é logada.
"""
from __future__ import annotations

import os
from typing import Any

import requests

from providers_base import MediaProvider


class WikimediaProvider(MediaProvider):
    name = "wikimedia"
    needs_key = False
    env_key = None

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": f"filetype:{'video' if media_type == 'video' else 'bitmap'} {query}",
            "gsrlimit": per,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        }
        headers = {"User-Agent": "FacelessCloudStudio/1.0 (contato@example.com)"}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            if not resp.ok:
                return []
            data = resp.json()
            pages = (data.get("query") or {}).get("pages") or {}
            out = []
            for p in pages.values():
                ii = (p.get("imageinfo") or [{}])[0]
                ext = ii.get("extmetadata") or {}
                out.append({
                    "provider": self.name,
                    "id": p.get("title", ""),
                    "url_origem": ii.get("url", ""),
                    "thumbnail": ii.get("thumburl", ii.get("url", "")),
                    "license": (ext.get("LicenseShortName") or {}).get("value", ""),
                    "author": (ext.get("Artist") or {}).get("value", ""),
                    "photographer": (ext.get("Artist") or {}).get("value", ""),
                    "requires_attribution": True,
                    "width": ii.get("width", 0),
                    "height": ii.get("height", 0),
                    "duration": 0.0,
                    "media_type": "video" if "video" in str(ii.get("mime", "")) else "image",
                })
            return out
        except Exception:
            return []


class NasaProvider(MediaProvider):
    name = "nasa"
    needs_key = False
    env_key = None

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        try:
            resp = requests.get("https://images-api.nasa.gov/search",
                                params={"q": query, "media_type": "video" if media_type == "video" else "image"},
                                timeout=20)
            if not resp.ok:
                return []
            items = (resp.json().get("collection") or {}).get("item", [])
            out = []
            for it in items[:per]:
                data = (it.get("data") or [{}])[0]
                links = it.get("links") or []
                href = links[0].get("href", "") if links else ""
                out.append({
                    "provider": self.name,
                    "id": data.get("nasa_id", ""),
                    "url_origem": href,
                    "thumbnail": href,
                    "license": "NASA",
                    "author": data.get("center", "NASA"),
                    "photographer": data.get("center", "NASA"),
                    "requires_attribution": True,
                    "width": 0,
                    "height": 0,
                    "duration": 0.0,
                    "media_type": media_type,
                })
            return out
        except Exception:
            return []


class OpenverseProvider(MediaProvider):
    name = "openverse"
    needs_key = False
    env_key = None

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        # Openverse não tem vídeo — só imagem e áudio
        if media_type == "video":
            return []
        try:
            resp = requests.get("https://api.openverse.org/v1/images/",
                                params={"q": query, "license_type": "commercial", "page_size": per},
                                timeout=20)
            if not resp.ok:
                return []
            results = resp.json().get("results", [])
            out = []
            for it in results:
                out.append({
                    "provider": self.name,
                    "id": it.get("id", ""),
                    "url_origem": it.get("url", ""),
                    "thumbnail": it.get("thumbnail", ""),
                    "license": it.get("license", ""),
                    "author": it.get("creator", ""),
                    "photographer": it.get("creator", ""),
                    "requires_attribution": bool(it.get("license")),
                    "width": it.get("width", 0),
                    "height": it.get("height", 0),
                    "duration": 0.0,
                    "media_type": "image",
                })
            return out
        except Exception:
            return []


class PexelsProvider(MediaProvider):
    name = "pexels"
    needs_key = True
    env_key = "PEXELS_API_KEY"

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            return []
        try:
            endpoint = "https://api.pexels.com/v1/videos/search" if media_type == "video" else "https://api.pexels.com/v1/search"
            params = {"query": query, "per_page": per}
            if media_type == "video":
                params["orientation"] = orientation
            resp = requests.get(endpoint, headers={"Authorization": key}, params=params, timeout=20)
            if not resp.ok:
                return []
            data = resp.json()
            items = data.get("videos") if media_type == "video" else data.get("photos", [])
            out = []
            for it in items:
                out.append({
                    "provider": self.name,
                    "id": str(it.get("id", "")),
                    "url_origem": it.get("url", ""),
                    "thumbnail": (it.get("image") or it.get("src", {}) or {}).get("original", ""),
                    "license": "Pexels",
                    "author": it.get("user", {}).get("name", "") if media_type == "video" else it.get("photographer", ""),
                    "photographer": it.get("photographer", ""),
                    "requires_attribution": True,
                    "width": it.get("width", 0),
                    "height": it.get("height", 0),
                    "duration": it.get("duration", 0.0) if media_type == "video" else 0.0,
                    "media_type": media_type,
                })
            return out
        except Exception:
            return []


class PixabayProvider(MediaProvider):
    name = "pixabay"
    needs_key = True
    env_key = "PIXABAY_API_KEY"

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            return []
        try:
            resp = requests.get("https://pixabay.com/api/videos/",
                                params={"key": key, "q": query, "video_type": "film",
                                        "min_width": 1920, "per_page": per},
                                timeout=20)
            if not resp.ok:
                return []
            hits = resp.json().get("hits", [])
            out = []
            for it in hits:
                videos = it.get("videos", {})
                best = videos.get("large") or videos.get("medium") or {}
                out.append({
                    "provider": self.name,
                    "id": str(it.get("id", "")),
                    "url_origem": best.get("url", ""),
                    "thumbnail": it.get("picture_id", "") and it.get("userImageURL", ""),
                    "license": "Pixabay",
                    "author": it.get("user", ""),
                    "photographer": it.get("user", ""),
                    "requires_attribution": True,
                    "width": best.get("width", 0),
                    "height": best.get("height", 0),
                    "duration": it.get("duration", 0.0),
                    "media_type": "video",
                })
            return out
        except Exception:
            return []


class NaraProvider(MediaProvider):
    name = "nara"
    needs_key = True
    env_key = "NARA_API_KEY"

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None) -> list[dict[str, Any]]:
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            return []
        try:
            resp = requests.get("https://catalog.archives.gov/api/v2/records/search",
                                params={"q": query, "availableOnline": "true"},
                                headers={"x-api-key": key}, timeout=20)
            if not resp.ok:
                return []
            results = resp.json().get("results", [])
            out = []
            for it in results[:per]:
                out.append({
                    "provider": self.name,
                    "id": str(it.get("identifier", "")),
                    "url_origem": it.get("online_link", ""),
                    "thumbnail": "",
                    "license": "NARA",
                    "author": "U.S. National Archives",
                    "photographer": "U.S. National Archives",
                    "requires_attribution": True,
                    "width": 0,
                    "height": 0,
                    "duration": 0.0,
                    "media_type": media_type,
                })
            return out
        except Exception:
            return []


class YouTubeProvider(MediaProvider):
    name = "youtube"
    needs_key = True
    env_key = "YOUTUBE_API_KEY"

    async def search(self, query: str, per: int = 6, orientation: str = "landscape",
                     media_type: str = "any", min_duration: int | None = None,
                     max_duration: int | None = None,
                     somente_creative_commons: bool = True) -> list[dict[str, Any]]:
        """Busca vídeos do YouTube (apenas CC por padrão). Não faz download automático."""
        key = os.getenv(self.env_key or "", "").strip()
        if not key:
            return []
        try:
            params = {
                "part": "snippet",
                "type": "video",
                "q": query,
                "maxResults": per,
                "key": key,
                "relevanceLanguage": "pt",
            }
            if somente_creative_commons:
                params["videoLicense"] = "creativeCommon"
            resp = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=20)
            if not resp.ok:
                return []
            items = resp.json().get("items", [])
            out = []
            for it in items:
                sn = it.get("snippet", {})
                out.append({
                    "provider": self.name,
                    "id": it.get("id", {}).get("videoId", ""),
                    "url_origem": f"https://www.youtube.com/watch?v={it.get('id', {}).get('videoId', '')}",
                    "thumbnail": (sn.get("thumbnails") or {}).get("high", {}).get("url", ""),
                    "license": "CC-BY" if somente_creative_commons else "YouTube",
                    "author": sn.get("channelTitle", ""),
                    "photographer": sn.get("channelTitle", ""),
                    "requires_attribution": True,
                    "width": 0,
                    "height": 0,
                    "duration": 0.0,
                    "media_type": "video",
                })
            return out
        except Exception:
            return []


# Registro de provedores disponíveis (instâncias)
PROVIDERS: list[MediaProvider] = [
    WikimediaProvider(),
    NasaProvider(),
    NaraProvider(),
    OpenverseProvider(),
    PexelsProvider(),
    PixabayProvider(),
    YouTubeProvider(),
]


def get_provider(name: str) -> MediaProvider | None:
    for p in PROVIDERS:
        if p.name == name:
            return p
    return None
