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


def _signed_params(resource: str, api_key: str, api_secret: str) -> dict[str, str]:
    """Gera os parâmetros HMAC exigidos pela API Storyblocks v2."""
    expires = str(int(time.time()) + 60 * 10)
    message_key = (api_secret + expires).encode("utf-8")
    signature = hmac.new(message_key, resource.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"APIKEY": api_key, "EXPIRES": expires, "HMAC": signature}


def storyblocks_search(
    query: str,
    api_key: str,
    media_type: str = "video",
    per: int = 4,
    orientation: str = "landscape",
    *,
    api_secret: str | None = None,
    project_id: str = "faceless-media-library",
    user_id: str = "faceless-local-user",
) -> list[dict[str, Any]]:
    """Busca vídeos ou imagens usando autenticação HMAC oficial (sem expor o segredo)."""
    secret = (api_secret or os.getenv("STORYBLOCKS_API_SECRET", "")).strip()
    if not is_active_key(api_key) or not is_active_key(secret):
        raise RuntimeError("Configure a API Key pública e a Secret Key do Storyblocks na tela Chaves de API.")
    query = " ".join(str(query or "").split())[:180]
    if not query:
        return []
    media_type = "image" if media_type == "image" else "video"
    project_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(project_id or ""))[:100] or "faceless-media-library"
    user_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(user_id or ""))[:100] or "faceless-local-user"

    cache_key = f"storyblocks|{media_type}|{per}|{orientation}|{project_id}|{query.lower()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached

    resource = f"/api/v2/{'videos' if media_type == 'video' else 'images'}/search"
    endpoint = "https://api.storyblocks.com" + resource
    params: dict[str, Any] = {
        "project_id": project_id,
        "user_id": user_id,
        "keywords": query,
        "page": 1,
        "results_per_page": max(1, min(12, int(per))),
        "sort_by": "most_relevant",
        "safe_search": "true",
        "extended": "keywords,description",
    }
    if orientation in ("portrait", "landscape", "square"):
        params["orientation"] = orientation
    params.update(_signed_params(resource, api_key, secret))

    response = requests.get(endpoint, params=params, headers={
        "User-Agent": "FacelessCloudStudio/0.5",
        "Accept": "application/json",
    }, timeout=30)
    if response.status_code in (401, 403):
        raise RuntimeError("Storyblocks recusou as credenciais. Confira API Key, Secret Key e permissões da API.")
    if not response.ok:
        detail = response.text[:240].replace("\n", " ")
        raise RuntimeError(f"Storyblocks API respondeu HTTP {response.status_code}: {detail}")
    data = response.json()
    results = data.get("results") or data.get("data") or data.get("items") or []
    options: list[dict[str, Any]] = []
    query_words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}

    for item in results:
        asset_id = item.get("id") or item.get("stock_item_id") or ""
        if not asset_id:
            continue
        title = str(item.get("title") or item.get("name") or "Storyblocks item")[:140]
        description = str(item.get("description") or item.get("caption") or "")[:240]
        author = item.get("author") or item.get("artist") or item.get("contributor") or "Storyblocks Contributor"
        if isinstance(author, dict):
            author = author.get("name") or author.get("title") or "Storyblocks Contributor"

        thumb = _first_url(item.get("thumbnail_url")) or _first_url(item.get("thumbnail")) or _first_url(item.get("preview_image_url"))
        preview_urls = item.get("preview_urls") or {}
        preview = (
            item.get("preview_url")
            or preview_urls.get("_720p")
            or preview_urls.get("_480p")
            or preview_urls.get("_360p")
            or preview_urls.get("_180p")
            or item.get("small_preview_url")
            or thumb
        )
        if isinstance(preview, dict):
            preview = _first_url(preview)
        dur = _duration(item.get("duration"))
        width = item.get("width") or item.get("video_width")
        height = item.get("height") or item.get("video_height")
        tags = item.get("keywords") or item.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
        blob = f"{title} {description} {' '.join(str(t) for t in tags)}".lower()
        overlap = sum(1 for word in query_words if word in blob)
        item_url = item.get("url") or "https://www.storyblocks.com/"

        options.append(_asset_option(
            provider="Storyblocks",
            media_type=media_type,
            asset_id=f"sb_{asset_id}",
            download_url=str(preview or ""),
            thumbnail=str(thumb or preview or ""),
            source_url=str(item_url),
            creator=str(author)[:80],
            license_name="Storyblocks · requer licença/download pela conta",
            width=int(width) if str(width or "").isdigit() else None,
            height=int(height) if str(height or "").isdigit() else None,
            duration=dur,
            title=title,
            description=description,
            tags=[str(t)[:40] for t in tags][:12],
            relevance=round(overlap / max(1, len(query_words)), 3),
            preview_only=True,
        ))

    if options:
        _cache_write(cache_key, options)
    return options
