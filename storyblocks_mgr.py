"""Integração com banco de vídeos e imagens do Storyblocks."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from keys_mgr import is_active_key
from store import DATA_DIR

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

_CACHE_DIR = DATA_DIR / "provider_cache"
_CACHE_TTL = 24 * 60 * 60


def _cache_read(key: str) -> list[dict[str, Any]] | None:
    path = _CACHE_DIR / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"
    try:
        if path.exists() and (time.time() - path.stat().st_mtime) < _CACHE_TTL:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _cache_write(key: str, value: list[dict[str, Any]]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _first_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("url", "src", "mp4", "mp4_download", "preview_url", "thumbnail_url"):
            if value.get(key):
                return str(value[key])
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _first_url(item)
            if found:
                return found
    return ""


def _duration(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return round(float(value), 1)
    if isinstance(value, str) and ":" in value:
        try:
            parts = [float(p) for p in value.split(":")]
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + part
            return round(seconds, 1) if seconds > 0 else None
        except ValueError:
            return None
    return None


def _asset_option(
    *,
    provider: str,
    media_type: str,
    asset_id: Any,
    download_url: str,
    thumbnail: str,
    source_url: str,
    creator: str = "",
    license_name: str = "Storyblocks License",
    width: int | None = None,
    height: int | None = None,
    duration: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    option = {
        "id": str(asset_id),
        "provider": provider,
        "media_type": media_type,
        "download_url": download_url,
        "thumbnail": thumbnail or download_url,
        "source_url": source_url,
        "photographer": creator or provider,
        "license": license_name,
        "width": width,
        "height": height,
        "duration": duration,
    }
    for key in ("title", "tags", "description", "downloads", "likes", "views", "relevance"):
        if extra.get(key) not in (None, "", []):
            option[key] = extra[key]
    return option


def storyblocks_search(
    query: str,
    api_key: str,
    media_type: str = "video",
    per: int = 4,
    orientation: str = "landscape",
) -> list[dict[str, Any]]:
    """Busca vídeos ou fotos na API do Storyblocks, com cache de 24 h."""
    if not is_active_key(api_key):
        return []
    query = " ".join(str(query or "").split())
    if not query:
        return []

    cache_key = f"storyblocks|{media_type}|{per}|{orientation}|{query.lower()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "FacelessCloudStudio/0.4",
        "Accept": "application/json",
    }

    endpoint = "https://api.storyblocks.com/api/v2/videos/search" if media_type == "video" else "https://api.storyblocks.com/api/v2/images/search"
    params = {
        "keywords": query,
        "num_results": max(1, min(12, per)),
        "page": 1,
    }
    if orientation == "portrait":
        params["orientation"] = "vertical"
    elif orientation == "landscape":
        params["orientation"] = "horizontal"

    try:
        r = requests.get(endpoint, headers=headers, params=params, timeout=25)
        if r.status_code in (401, 403) and media_type == "image":
            # Tenta via GraphicStock se a conta for de imagens
            r = requests.get("https://api.graphicstock.com/api/v2/images/search", headers=headers, params=params, timeout=25)
        if not r.ok:
            return []

        data = r.json()
        results = data.get("results") or data.get("data") or data.get("items") or []
        options: list[dict[str, Any]] = []
        query_words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}

        for item in results:
            asset_id = item.get("id") or item.get("stock_item_id") or ""
            title = str(item.get("title") or item.get("name") or "Storyblocks item")[:140]
            description = str(item.get("description") or item.get("caption") or "")[:240]
            author = item.get("author") or item.get("artist") or item.get("contributor") or "Storyblocks Contributor"
            if isinstance(author, dict):
                author = author.get("name") or author.get("title") or "Storyblocks Contributor"

            thumb = (
                _first_url(item.get("thumbnail_url"))
                or _first_url(item.get("thumbnail"))
                or _first_url(item.get("preview_url"))
                or _first_url(item.get("preview_image_url"))
                or _first_url(item.get("previews"))
                or _first_url(item.get("images"))
            )
            download_url = (
                _first_url(item.get("download_url"))
                or _first_url(item.get("preview_video_url"))
                or _first_url(item.get("preview_url"))
                or _first_url(item.get("videos"))
                or thumb
            )

            dur = _duration(item.get("duration"))
            w = item.get("width") or item.get("video_width") or (1280 if orientation != "portrait" else 720)
            h = item.get("height") or item.get("video_height") or (720 if orientation != "portrait" else 1280)
            tags = item.get("keywords") or item.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
            blob = f"{title} {description} {' '.join(str(t) for t in tags)}".lower()
            overlap = sum(1 for word in query_words if word in blob)

            if download_url:
                options.append(_asset_option(
                    provider="Storyblocks",
                    media_type=media_type,
                    asset_id=f"sb_{asset_id}",
                    download_url=download_url,
                    thumbnail=thumb or download_url,
                    source_url=item.get("url") or f"https://www.storyblocks.com/{'video' if media_type == 'video' else 'image'}/{asset_id}",
                    creator=str(author)[:80],
                    license_name="Storyblocks Royalty-Free License",
                    width=int(w) if str(w).isdigit() else None,
                    height=int(h) if str(h).isdigit() else None,
                    duration=dur,
                    title=title,
                    description=description,
                    tags=[str(t)[:40] for t in tags][:12],
                    downloads=item.get("downloads") or item.get("download_count"),
                    views=item.get("views") or item.get("view_count"),
                    likes=item.get("likes"),
                    relevance=round(overlap / max(1, len(query_words)), 3),
                ))

        if options:
            _cache_write(cache_key, options)
        return options
    except Exception:
        return []
