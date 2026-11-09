"""Bancos de mídia: catálogo, busca por cena e ordenação das opções."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime
from typing import Any

import requests

from keys_mgr import is_active_key
from store import DATA_DIR
import storyblocks_mgr
import youtube_mgr

# Catálogo mostrado na interface. A chave "env" indica qual Secret ativa a fonte.
SOURCES: list[dict[str, Any]] = [
    {"id": "youtube_video", "provider": "YouTube", "kind": "video", "env": None, "blurb": "Vídeos do YouTube (confira os direitos de uso antes de publicar)", "link": "https://www.youtube.com"},
    {"id": "youtube_frame", "provider": "YouTube · quadro", "kind": "image", "env": None, "blurb": "Extrai um quadro de até dez segundos de vídeo. Desmarcado por padrão; use somente com autorização.", "link": "https://www.youtube.com"},
    {"id": "storyblocks_video", "provider": "Storyblocks", "kind": "video", "env": "STORYBLOCKS_API_KEY", "blurb": "Vídeos cinematográficos do Storyblocks", "link": "https://www.storyblocks.com"},
    {"id": "storyblocks_image", "provider": "Storyblocks", "kind": "image", "env": "STORYBLOCKS_API_KEY", "blurb": "Imagens e ilustrações do Storyblocks", "link": "https://www.storyblocks.com"},
    {"id": "pexels_video", "provider": "Pexels", "kind": "video", "env": "PEXELS_API_KEY", "blurb": "Vídeos stock em boa qualidade", "link": "https://www.pexels.com/api/"},
    {"id": "pixabay_video", "provider": "Pixabay", "kind": "video", "env": "PIXABAY_API_KEY", "blurb": "Vídeos livres, resultados em cache por 24 h", "link": "https://pixabay.com/api/docs/"},
    {"id": "coverr_video", "provider": "Coverr", "kind": "video", "env": "COVERR_API_KEY", "blurb": "Vídeos stock reais, exige crédito ao autor", "link": "https://coverr.co/developers"},
    {"id": "wikimedia_video", "provider": "Wikimedia Commons", "kind": "video", "env": None, "blurb": "Arquivos históricos e documentais, licenças variadas", "link": "https://commons.wikimedia.org/"},
    {"id": "pexels_image", "provider": "Pexels", "kind": "image", "env": "PEXELS_API_KEY", "blurb": "Fotos de alta resolução", "link": "https://www.pexels.com/api/"},
    {"id": "pixabay_image", "provider": "Pixabay", "kind": "image", "env": "PIXABAY_API_KEY", "blurb": "Fotos e ilustrações livres", "link": "https://pixabay.com/api/docs/"},
    {"id": "unsplash_image", "provider": "Unsplash", "kind": "image", "env": "UNSPLASH_ACCESS_KEY", "blurb": "Fotos artísticas, exige atribuição", "link": "https://unsplash.com/developers"},
    {"id": "openverse_image", "provider": "Openverse", "kind": "image", "env": None, "blurb": "Obras abertas com licença Creative Commons", "link": "https://openverse.org/"},
    {"id": "wikimedia_image", "provider": "Wikimedia Commons", "kind": "image", "env": None, "blurb": "Fotos históricas e de domínio público", "link": "https://commons.wikimedia.org/"},
]
SOURCE_IDS = {s["id"] for s in SOURCES}


def public_sources() -> list[dict[str, Any]]:
    out = []
    for s in SOURCES:
        ready = True if not s["env"] else is_active_key(os.getenv(s["env"], ""))
        if s["provider"] == "Storyblocks":
            ready = ready and is_active_key(os.getenv("STORYBLOCKS_API_SECRET", ""))
        out.append({**s, "ready": ready, "needs_key": bool(s["env"])})
    return out


def provider_key(env_name: str, provider_name: str) -> str:
    key = os.getenv(env_name, "").strip()
    if not is_active_key(key):
        raise RuntimeError(f"{provider_name}: configure {env_name} na tela de Chaves para ativar esta fonte.")
    return key


def orientation_for(ratio: str) -> str:
    return {"9:16": "portrait", "1:1": "square"}.get(ratio, "landscape")


def _asset_option(*, provider: str, media_type: str, asset_id: Any, download_url: str, thumbnail: str,
                  source_url: str, creator: str = "", license_name: str = "", width: int | None = None,
                  height: int | None = None, duration: float | None = None,
                  download_location: str | None = None, **extra: Any) -> dict[str, Any]:
    option = {
        "id": str(asset_id), "provider": provider, "media_type": media_type,
        "download_url": download_url, "thumbnail": thumbnail or download_url,
        "source_url": source_url, "photographer": creator or provider,
        "license": license_name, "width": width, "height": height,
        "duration": duration, "download_location": download_location,
    }
    for key in ("title", "tags", "description", "downloads", "likes", "views", "relevance", "preview_only", "requires_permission", "frame_from_video"):
        if extra.get(key) not in (None, "", []):
            option[key] = extra[key]
    return option


# ------------------------------------------------------------------ cache e ranking

_CACHE_DIR = DATA_DIR / "provider_cache"
_CACHE_TTL = 24 * 60 * 60


def _cache_read(key: str) -> Any | None:
    path = _CACHE_DIR / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"
    try:
        if path.exists() and (datetime.now().timestamp() - path.stat().st_mtime) < _CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _cache_write(key: str, value: Any) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _cached(key: str, loader):
    cached = _cache_read(key)
    if cached is not None:
        return cached
    value = loader()
    if value:
        _cache_write(key, value)
    return value


def _words(value: Any) -> set[str]:
    text = " ".join(str(x) for x in (value if isinstance(value, (list, tuple)) else [value]))
    return {w for w in re.findall(r"[a-z0-9À-ÿ]+", text.lower()) if len(w) > 1}


def _decorate(options: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Calcula relevância textual e uma nota final para ordenar as opções."""
    q = _words(query)
    for option in options:
        blob = " ".join(str(option.get(k, "")) for k in ("title", "tags", "description", "photographer"))
        tokens = _words(blob)
        overlap = len(q & tokens) / max(1, len(q))
        if not isinstance(option.get("relevance"), (int, float)):
            option["relevance"] = round(overlap, 3)
        w, h = int(option.get("width") or 0), int(option.get("height") or 0)
        short = min(w, h) if w and h else 0
        quality = 0.0
        if short >= 2160:
            quality = 3.0
        elif short >= 1080:
            quality = 2.4
        elif short >= 720:
            quality = 1.6
        elif short >= 480:
            quality = 0.8
        popularity = option.get("downloads") or option.get("likes") or option.get("views") or 0
        try:
            popularity = math.log10(float(popularity) + 1) * 0.4
        except (TypeError, ValueError):
            popularity = 0.0
        option["rank"] = round(float(option.get("relevance") or 0) * 5 + quality + min(2.0, popularity), 3)
    return options


def pexels_search(query: str, api_key: str, media_type: str, per: int, orientation: str) -> list[dict[str, Any]]:
    cache_key = f"pexels|{media_type}|{per}|{orientation}|{query.lower().strip()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": per, "orientation": orientation}
    if media_type == "video":
        response = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=35)
        response.raise_for_status()
        options = []
        for video in response.json().get("videos", []):
            files = [f for f in video.get("video_files", []) if f.get("link") and f.get("file_type") == "video/mp4"]
            if not files:
                continue
            # prefere ~720p: não baixa originais 4K
            files.sort(key=lambda f: (abs(max(f.get("width") or 0, f.get("height") or 0) - 1280), max(f.get("width") or 0, f.get("height") or 0) > 1920))
            chosen = files[0]
            options.append(_asset_option(
                provider="Pexels", media_type="video", asset_id=video.get("id", ""),
                download_url=chosen["link"], thumbnail=video.get("image", ""),
                source_url=video.get("url", ""), creator=video.get("user", {}).get("name", "Pexels creator"),
                license_name="Pexels License", width=chosen.get("width"), height=chosen.get("height"),
                duration=video.get("duration"), tags=video.get("tags"), description=video.get("url", ""),
            ))
        _cache_write(cache_key, options)
        return options
    response = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=35)
    response.raise_for_status()
    options = []
    for photo in response.json().get("photos", []):
        src = photo.get("src", {})
        download = src.get("large2x") or src.get("large") or src.get("original")
        if not download:
            continue
        options.append(_asset_option(
            provider="Pexels", media_type="image", asset_id=photo.get("id", ""),
            download_url=download, thumbnail=src.get("medium") or src.get("small") or download,
            source_url=photo.get("url", ""), creator=photo.get("photographer", "Pexels creator"),
            license_name="Pexels License", width=photo.get("width"), height=photo.get("height"),
            title=(photo.get("alt") or "")[:140], description=photo.get("alt") or "",
        ))
    _cache_write(cache_key, options)
    return options


def pixabay_search(query: str, api_key: str, media_type: str, per: int, orientation: str) -> list[dict[str, Any]]:
    # A Pixabay pede cache de 24 h nas respostas.
    cache_dir = DATA_DIR / "provider_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(f"pixabay|{media_type}|{per}|{orientation}|{query.lower().strip()}".encode("utf-8")).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    if cache_file.exists() and (datetime.now().timestamp() - cache_file.stat().st_mtime) < 24 * 60 * 60:
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    endpoint = "https://pixabay.com/api/videos/" if media_type == "video" else "https://pixabay.com/api/"
    params: dict[str, Any] = {"key": api_key, "q": query, "per_page": max(3, per), "safesearch": "true"}
    if media_type == "image" and orientation in ("landscape", "portrait"):
        params["orientation"] = "horizontal" if orientation == "landscape" else "vertical"
    response = requests.get(endpoint, params=params, timeout=35)
    response.raise_for_status()
    payload = response.json()
    options = []
    if media_type == "video":
        for video in payload.get("hits", [])[:per]:
            variants = video.get("videos", {})
            candidates = [variants.get(k) for k in ("medium", "small", "large", "tiny") if variants.get(k, {}).get("url")]
            if not candidates:
                continue
            candidates.sort(key=lambda f: abs((f.get("width") or 720) - 1280))
            selected = candidates[0]
            options.append(_asset_option(
                provider="Pixabay", media_type="video", asset_id=video.get("id", ""),
                download_url=selected["url"], thumbnail=selected.get("thumbnail") or video.get("userImageURL", ""),
                source_url=video.get("pageURL", ""), creator=video.get("user", "Pixabay creator"),
                license_name="Pixabay Content License", width=selected.get("width"), height=selected.get("height"),
                duration=video.get("duration"), tags=video.get("tags"), likes=video.get("likes"),
                downloads=video.get("downloads"), views=video.get("views"),
                title=(video.get("tags") or "")[:140],
            ))
    else:
        for photo in payload.get("hits", [])[:per]:
            download = photo.get("largeImageURL") or photo.get("webformatURL")
            if not download:
                continue
            options.append(_asset_option(
                provider="Pixabay", media_type="image", asset_id=photo.get("id", ""),
                download_url=download, thumbnail=photo.get("previewURL") or photo.get("webformatURL"),
                source_url=photo.get("pageURL", ""), creator=photo.get("user", "Pixabay creator"),
                license_name="Pixabay Content License", width=photo.get("imageWidth"), height=photo.get("imageHeight"),
                tags=photo.get("tags"), likes=photo.get("likes"), downloads=photo.get("downloads"),
                views=photo.get("views"), title=(photo.get("tags") or "")[:140],
            ))
    cache_file.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
    return options


def coverr_search(query: str, api_key: str, per: int) -> list[dict[str, Any]]:
    """API oficial da Coverr, só stock real (sem conteúdo gerado por IA)."""
    cache_key = f"coverr|{per}|{query.lower().strip()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached
    response = requests.get(
        "https://api.coverr.co/videos", headers={"x-api-key": api_key},
        params={"query": query, "page_size": per, "urls": "true", "filter": "is_ai_generated:false"}, timeout=35,
    )
    response.raise_for_status()
    options: list[dict[str, Any]] = []
    for video in response.json().get("hits", []):
        urls = video.get("urls") or {}
        download = urls.get("mp4_download") or urls.get("mp4")
        if not download:
            continue
        if video.get("is_sponsored") or video.get("sponsored") or video.get("partner_content") or video.get("is_premium"):
            continue
        author = video.get("creator") or video.get("author") or video.get("user") or "Coverr"
        if isinstance(author, dict):
            author = author.get("name") or author.get("title") or "Coverr"
        options.append(_asset_option(
            provider="Coverr", media_type="video", asset_id=video.get("id", ""),
            download_url=download, thumbnail=video.get("thumbnail") or video.get("poster", ""),
            source_url="https://coverr.co/", creator=str(author),
            license_name="Coverr Stock License · atribuição obrigatória na conta Demo",
            width=video.get("max_width"), height=video.get("max_height"), duration=video.get("duration"),
            title=(video.get("title") or video.get("description") or "")[:140], tags=video.get("tags"),
            description=video.get("description") or "",
        ))
    _cache_write(cache_key, options)
    return options


def unsplash_search(query: str, api_key: str, per: int, orientation: str) -> list[dict[str, Any]]:
    cache_key = f"unsplash|{per}|{orientation}|{query.lower().strip()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached
    response = requests.get(
        "https://api.unsplash.com/search/photos", headers={"Authorization": f"Client-ID {api_key}"},
        params={"query": query, "per_page": per, "orientation": "squarish" if orientation == "square" else orientation, "content_filter": "high"},
        timeout=35,
    )
    response.raise_for_status()
    options = []
    for photo in response.json().get("results", []):
        urls = photo.get("urls", {})
        links = photo.get("links", {})
        download = urls.get("regular") or urls.get("full")
        if not download:
            continue
        tags = photo.get("tags") or []
        options.append(_asset_option(
            provider="Unsplash", media_type="image", asset_id=photo.get("id", ""),
            download_url=download, thumbnail=urls.get("small") or urls.get("thumb") or download,
            source_url=links.get("html", ""), creator=photo.get("user", {}).get("name", "Unsplash creator"),
            license_name="Unsplash License", width=photo.get("width"), height=photo.get("height"),
            download_location=links.get("download_location"),
            title=(photo.get("alt_description") or photo.get("description") or "")[:140],
            description=(photo.get("description") or photo.get("alt_description") or ""),
            tags=[t.get("title") for t in tags if isinstance(t, dict) and t.get("title")],
            likes=photo.get("likes"), downloads=photo.get("downloads"),
        ))
    _cache_write(cache_key, options)
    return options


def openverse_search(query: str, per: int) -> list[dict[str, Any]]:
    cache_key = f"openverse|{per}|{query.lower().strip()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached
    response = requests.get(
        "https://api.openverse.org/v1/images/", params={"q": query, "page_size": per, "mature": "false"},
        headers={"User-Agent": "FacelessCloudStudio/0.4 (media search tool)"}, timeout=35,
    )
    response.raise_for_status()
    options = []
    for item in response.json().get("results", []):
        download = item.get("url")
        if not download:
            continue
        tags = item.get("tags") or []
        options.append(_asset_option(
            provider="Openverse", media_type="image", asset_id=item.get("id", ""),
            download_url=download, thumbnail=item.get("thumbnail") or download,
            source_url=item.get("foreign_landing_url") or item.get("detail_url", ""),
            creator=item.get("creator") or "Autor não informado",
            license_name=f"{item.get('license', 'Licença não informada')} {item.get('license_version', '')}".strip(),
            width=item.get("width"), height=item.get("height"),
            title=(item.get("title") or "")[:140],
            tags=[t.get("name") for t in tags if isinstance(t, dict) and t.get("name")],
        ))
    _cache_write(cache_key, options)
    return options


_WIKIMEDIA_THROTTLED: set[str] = set()  # project ids where wikimedia was rate-limited


def wikimedia_search(query: str, media_type: str, per: int, project_id: str = "") -> list[dict[str, Any]]:
    if project_id and project_id in _WIKIMEDIA_THROTTLED:
        return []
    cache_key = f"wikimedia|{media_type}|{per}|{query.lower().strip()}"
    cached = _cache_read(cache_key)
    if cached is not None:
        return cached
    file_filter = "video" if media_type == "video" else "bitmap"
    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "search", "gsrsearch": f"filetype:{file_filter} {query}",
                "gsrnamespace": 6, "gsrlimit": per, "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size",
                "iiurlwidth": 1200, "format": "json",
            },
            headers={"User-Agent": "FacelessCloudStudio/0.4 (media search tool)"}, timeout=35,
        )
        if response.status_code == 429:
            if project_id:
                _WIKIMEDIA_THROTTLED.add(project_id)
            return []
        response.raise_for_status()
    except Exception:
        return []
    pages = response.json().get("query", {}).get("pages", {})
    options = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        ext = info.get("extmetadata", {})
        mime = str(info.get("mime", "")).lower()
        if media_type == "video" and not mime.startswith("video/"):
            continue
        if media_type == "image" and not mime.startswith("image/"):
            continue
        download = info.get("url") if media_type == "video" else (info.get("thumburl") or info.get("url"))
        if not download:
            continue
        creator = re.sub(r"<[^>]+>", "", ext.get("Artist", {}).get("value", "Autor não informado"))
        license_name = ext.get("LicenseShortName", {}).get("value", "Licença a verificar")
        description = re.sub(r"<[^>]+>", "", ext.get("ImageDescription", {}).get("value", ""))
        options.append(_asset_option(
            provider="Wikimedia Commons", media_type=media_type, asset_id=page.get("pageid", ""),
            download_url=download, thumbnail=info.get("thumburl") or info.get("descriptionurl", "") or download,
            source_url=info.get("descriptionurl", ""), creator=creator[:140], license_name=license_name,
            width=info.get("width"), height=info.get("height"),
            title=re.sub(r"^File:", "", str(page.get("title", "")))[:140], description=description[:240],
        ))
    if options:
        _cache_write(cache_key, options)
    return options


def order_options(options: list[dict[str, Any]], pref: str) -> list[dict[str, Any]]:
    """Intercala as fontes e depois ordena por relevância/qualidade técnica."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for option in options:
        by_source.setdefault(f"{option.get('provider')}|{option.get('media_type')}", []).append(option)
    mixed: list[dict[str, Any]] = []
    queues = list(by_source.values())
    while any(queues):
        for q in queues:
            if q:
                mixed.append(q.pop(0))
    mixed.sort(key=lambda o: (
        0 if (pref in ("video", "image") and o.get("media_type") == pref) else 1,
        -float(o.get("rank") or 0),
    ))
    return mixed


def search_scene_assets(query: str, sources: list[str], source_counts: dict[str, int], *, per: int = 3,
                        orientation: str = "landscape", pref: str = "mixed", project_id: str = "",
                        queries: list[str] | None = None, smart: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    options: list[dict[str, Any]] = []
    messages: list[str] = []
    per = max(1, min(8, per))
    # Variantes: a principal primeiro; se o banco devolver pouco, tenta a curta.
    query_list: list[str] = []
    for value in ([query] + list(queries or [])):
        clean = " ".join(str(value or "").split())[:160]
        if clean and clean.lower() not in {q.lower() for q in query_list}:
            query_list.append(clean)
    if smart and len(query_list) == 1 and len(query.split()) > 3:
        query_list.append(" ".join(query.split()[:3]))
    query_list = query_list[:2]

    def run_source(source: str, q: str) -> None:
        nonlocal messages
        try:
            if source in ("youtube_video", "youtube_frame"):
                from scenes import make_youtube_query
                yt_query = make_youtube_query(q)
                found = youtube_mgr.youtube_search(yt_query, per=per, orientation=orientation)
                if source == "youtube_video":
                    options.extend(found)
                else:
                    # Apenas miniaturas públicas. Não baixa o vídeo nem presume licença de reutilização.
                    for item in found:
                        thumb = item.get("thumbnail")
                        if not thumb:
                            continue
                        options.append({
                            **item,
                            "id": f"{item.get('id', 'yt')}_thumbnail",
                            "provider": "YouTube · miniatura",
                            "media_type": "image",
                            "download_url": item.get("download_url") or item.get("source_url") or "",
                            "thumbnail": thumb,
                            "duration": None,
                            "license": "Quadro extraído do YouTube · reutilize somente com autorização",
                            "requires_permission": True,
                            "frame_from_video": True,
                        })
            elif source == "storyblocks_video":
                options.extend(storyblocks_mgr.storyblocks_search(
                    q, provider_key("STORYBLOCKS_API_KEY", "Storyblocks"), "video", per, orientation,
                    project_id=project_id or "faceless-auto-project",
                ))
            elif source == "storyblocks_image":
                options.extend(storyblocks_mgr.storyblocks_search(
                    q, provider_key("STORYBLOCKS_API_KEY", "Storyblocks"), "image", per, orientation,
                    project_id=project_id or "faceless-auto-project",
                ))
            elif source == "pexels_video":
                options.extend(pexels_search(q, provider_key("PEXELS_API_KEY", "Pexels"), "video", per, orientation))
            elif source == "pexels_image":
                options.extend(pexels_search(q, provider_key("PEXELS_API_KEY", "Pexels"), "image", per, orientation))
            elif source == "coverr_video":
                if source_counts.get(source, 0) >= int(os.getenv("COVERR_SCENE_SEARCH_LIMIT", "30")):
                    messages.append("Coverr: limite automático por projeto atingido.")
                    return
                options.extend(coverr_search(q, provider_key("COVERR_API_KEY", "Coverr"), per))
                source_counts[source] = source_counts.get(source, 0) + 1
            elif source in ("pixabay_video", "pixabay_image"):
                if source_counts.get(source, 0) >= int(os.getenv("PIXABAY_SCENE_SEARCH_LIMIT", "12")):
                    messages.append(f"Pixabay: limite automático por projeto atingido ({source}). Pesquise esta cena manualmente.")
                    return
                options.extend(pixabay_search(q, provider_key("PIXABAY_API_KEY", "Pixabay"), "video" if source.endswith("video") else "image", per, orientation))
                source_counts[source] = source_counts.get(source, 0) + 1
            elif source == "unsplash_image":
                if source_counts.get(source, 0) >= int(os.getenv("UNSPLASH_SCENE_SEARCH_LIMIT", "25")):
                    messages.append("Unsplash: limite automático por projeto atingido.")
                    return
                options.extend(unsplash_search(q, provider_key("UNSPLASH_ACCESS_KEY", "Unsplash"), per, orientation))
                source_counts[source] = source_counts.get(source, 0) + 1
            elif source == "openverse_image":
                options.extend(openverse_search(q, per))
            elif source == "wikimedia_image":
                options.extend(wikimedia_search(q, "image", per, project_id=project_id))
            elif source == "wikimedia_video":
                options.extend(wikimedia_search(q, "video", per, project_id=project_id))
        except Exception as exc:  # uma fonte com problema não derruba a busca das outras
            message = str(exc)[:220]
            if message not in messages:
                messages.append(message)

    for q_index, q in enumerate(query_list):
        for source in sources:
            run_source(source, q)
        deduped_now = {(o.get("provider"), o.get("id"), o.get("media_type")) for o in options}
        # Já há material suficiente? Não gasta chamadas extras na segunda variante.
        if q_index == 0 and len(deduped_now) >= max(6, per * 2):
            break

    seen = set()
    deduped = []
    for option in order_options(_decorate(options, query), pref):
        key = (option.get("provider"), option.get("id"), option.get("media_type"))
        if key not in seen:
            seen.add(key)
            deduped.append(option)
    return deduped[:20], messages
