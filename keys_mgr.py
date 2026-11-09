"""Gerenciamento, validação e teste de chaves de API do Faceless Cloud Studio."""
from __future__ import annotations

import os
from typing import Any

import requests
from store import BASE_DIR

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

PLACEHOLDER_PREFIXES = (
    "sua_chave", "your_key", "troque_por", "coloque_aqui", "insira_aqui", "sua_",
)

KEY_DEFINITIONS = [
    {
        "id": "pixabay",
        "env": "PIXABAY_API_KEY",
        "name": "Pixabay",
        "category": "Bancos de Mídia",
        "blurb": "Vídeos e fotos gratuitos para uso comercial sem atribuição.",
        "link": "https://pixabay.com/api/docs/",
        "kind": "video/image",
    },
    {
        "id": "pexels",
        "env": "PEXELS_API_KEY",
        "name": "Pexels",
        "category": "Bancos de Mídia",
        "blurb": "Vídeos stock e fotos de alta resolução.",
        "link": "https://www.pexels.com/api/",
        "kind": "video/image",
    },
    {
        "id": "unsplash",
        "env": "UNSPLASH_ACCESS_KEY",
        "name": "Unsplash",
        "category": "Bancos de Mídia",
        "blurb": "Fotos artísticas de alta qualidade (exige atribuição).",
        "link": "https://unsplash.com/developers",
        "kind": "image",
    },
    {
        "id": "coverr",
        "env": "COVERR_API_KEY",
        "name": "Coverr",
        "category": "Bancos de Mídia",
        "blurb": "Vídeos reais gravados por filmmakers.",
        "link": "https://coverr.co/developers",
        "kind": "video",
    },
    {
        "id": "storyblocks",
        "env": "STORYBLOCKS_API_KEY",
        "name": "Storyblocks · API Key",
        "category": "Bancos de Mídia",
        "blurb": "Chave pública para autenticar buscas no Storyblocks.",
        "link": "https://developer.storyblocks.com/",
        "kind": "video/image",
    },
    {
        "id": "storyblocks_secret",
        "env": "STORYBLOCKS_API_SECRET",
        "name": "Storyblocks · Secret Key",
        "category": "Bancos de Mídia",
        "blurb": "Chave secreta usada somente no servidor para assinar requisições HMAC. Nunca compartilhe esta chave.",
        "link": "https://developer.storyblocks.com/",
        "kind": "secret",
    },
    {
        "id": "youtube",
        "env": "YOUTUBE_API_KEY",
        "name": "YouTube API (Opcional)",
        "category": "YouTube",
        "blurb": "Chave da YouTube Data API v3 (o yt-dlp integrado já funciona mesmo sem chave).",
        "link": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
        "kind": "video",
    },
    {
        "id": "fish_audio",
        "env": "FISH_API_KEY",
        "name": "Fish Audio",
        "category": "Narração com IA",
        "blurb": "Vozes realistas de narradores para gerar o áudio MP3 e legendas.",
        "link": "https://fish.audio/app/api-keys",
        "kind": "audio",
    },
    {
        "id": "gemini",
        "env": "GEMINI_API_KEY",
        "name": "Google Gemini API (Flow AI)",
        "category": "Inteligência Artificial",
        "blurb": "Geração de imagem (Nano Banana/Imagen) e vídeo (Veo 3.1) via Google AI Studio.",
        "link": "https://aistudio.google.com/app/apikey",
        "kind": "ai",
    },
    {
        "id": "openrouter",
        "env": "OPENROUTER_API_KEY",
        "name": "OpenRouter · IA para busca visual",
        "category": "Inteligência Artificial",
        "blurb": "Interpreta cada cena do roteiro e cria consultas visuais. O Gemini e a busca tradicional continuam como fallback.",
        "link": "https://openrouter.ai/keys",
        "kind": "ai",
    },
    {
        "id": "groq",
        "env": "GROQ_API_KEY",
        "name": "Groq · Whisper (legendas exatas)",
        "category": "Inteligência Artificial",
        "blurb": "Transcrição da narração com horários por palavra para gerar SRT sincronizado.",
        "link": "https://console.groq.com/keys",
        "kind": "audio",
    },
    {
        "id": "app_password",
        "env": "APP_PASSWORD",
        "name": "Senha do Estúdio",
        "category": "Segurança",
        "blurb": "Protege o acesso à interface do Faceless Cloud Studio.",
        "link": "",
        "kind": "security",
    },
]


def is_placeholder(val: str | None) -> bool:
    if not val:
        return False
    v = val.strip().lower()
    if not v:
        return False
    for p in PLACEHOLDER_PREFIXES:
        if v.startswith(p):
            return True
    return False


def is_active_key(val: str | None) -> bool:
    if not val:
        return False
    v = val.strip()
    return bool(v) and not is_placeholder(v)


def mask_key(val: str | None) -> str:
    if not val:
        return ""
    v = val.strip()
    if is_placeholder(v):
        return f"[Exemplo de chave: {v}]"
    if len(v) <= 8:
        return "****"
    return f"{v[:4]}****{v[-4:]}"


def get_all_keys_status() -> list[dict[str, Any]]:
    result = []
    for item in KEY_DEFINITIONS:
        env_val = os.getenv(item["env"], "").strip()
        configured = is_active_key(env_val)
        placeholder = is_placeholder(env_val)
        result.append({
            "id": item["id"],
            "env": item["env"],
            "name": item["name"],
            "category": item["category"],
            "blurb": item["blurb"],
            "link": item["link"],
            "kind": item["kind"],
            "configured": configured,
            "placeholder": placeholder,
            "masked": mask_key(env_val),
            "has_value": bool(env_val),
        })
    return result


def save_env_keys(keys_map: dict[str, str]) -> None:
    """Salva as chaves no arquivo .env e atualiza os.environ em tempo real."""
    env_file = BASE_DIR / ".env"
    existing_lines = []
    if env_file.exists():
        existing_lines = env_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    lines_out: list[str] = []
    updated_keys = set()

    for line in existing_lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            k, _ = trimmed.split("=", 1)
            k = k.strip()
            if k in keys_map:
                new_val = keys_map[k].strip()
                lines_out.append(f"{k}={new_val}")
                os.environ[k] = new_val
                updated_keys.add(k)
                continue
        lines_out.append(line)

    # Chaves novas que não estavam no .env
    for k, v in keys_map.items():
        if k not in updated_keys:
            val_clean = v.strip()
            lines_out.append(f"{k}={val_clean}")
            os.environ[k] = val_clean

    env_file.write_text("\n".join(lines_out) + "\n", encoding="utf-8")


def test_provider_key(key_id: str, key_value: str | None = None) -> dict[str, Any]:
    """Testa a chave informada ou a que estiver em os.environ contra a API oficial."""
    target_env = next((item["env"] for item in KEY_DEFINITIONS if item["id"] == key_id), None)
    if not target_env:
        return {"ok": False, "message": f"Provedor desconhecido: {key_id}"}

    key = (key_value if key_value is not None else os.getenv(target_env, "")).strip()
    if not key:
        return {"ok": False, "message": f"Nenhuma chave informada para {target_env}."}
    if is_placeholder(key):
        return {"ok": False, "message": f"A chave é um texto de exemplo ({key}). Digite uma chave real."}

    try:
        if key_id == "pixabay":
            r = requests.get("https://pixabay.com/api/", params={"key": key, "q": "nature", "per_page": 3}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                total = data.get("totalHits", 0)
                return {"ok": True, "message": f"Conexão com Pixabay OK! Total de mídias encontradas no teste: {total}."}
            return {"ok": False, "message": f"Pixabay recusou a chave (código {r.status_code}): {r.text[:200]}"}

        elif key_id == "pexels":
            r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key}, params={"query": "nature", "per_page": 1}, timeout=15)
            if r.status_code == 200:
                return {"ok": True, "message": "Conexão com Pexels OK! Chave de API autorizada."}
            return {"ok": False, "message": f"Pexels recusou a chave (código {r.status_code}): {r.text[:200]}"}

        elif key_id == "unsplash":
            r = requests.get("https://api.unsplash.com/photos", headers={"Authorization": f"Client-ID {key}"}, params={"per_page": 1}, timeout=15)
            if r.status_code == 200:
                return {"ok": True, "message": "Conexão com Unsplash OK! Chave de acesso autorizada."}
            return {"ok": False, "message": f"Unsplash recusou a chave (código {r.status_code}): {r.text[:200]}"}

        elif key_id == "coverr":
            r = requests.get("https://api.coverr.co/videos", headers={"x-api-key": key}, params={"page_size": 1}, timeout=15)
            if r.status_code == 200:
                return {"ok": True, "message": "Conexão com Coverr OK! Chave de API autorizada."}
            return {"ok": False, "message": f"Coverr recusou a chave (código {r.status_code}): {r.text[:200]}"}

        elif key_id == "fish_audio":
            r = requests.get("https://api.fish.audio/model", headers={"Authorization": f"Bearer {key}"}, params={"page_size": 1, "self": "true"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                total = len(data.get("items", [])) if isinstance(data, dict) else 0
                return {"ok": True, "message": f"Conexão com Fish Audio OK! Chave ativa (vozes na conta: {total})."}
            return {"ok": False, "message": f"Fish Audio recusou a chave (código {r.status_code}): {r.text[:200]}"}

        elif key_id == "gemini":
            r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=5", timeout=15)
            if r.status_code == 200:
                models = [m.get("name", "").replace("models/", "") for m in r.json().get("models", [])]
                has_veo = any("veo" in m for m in models)
                extra = " (Veo detectado para geração de vídeo)" if has_veo else ""
                return {"ok": True, "message": f"Conexão com Gemini API / Google Flow OK!{extra}"}
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message", "")
            except Exception:
                detail = r.text[:200]
            return {"ok": False, "message": f"Google recusou a chave (código {r.status_code}): {detail}"}

        elif key_id == "youtube":
            # Testa via YouTube Data API v3 se houver chave, ou testa o motor yt-dlp
            r = requests.get("https://www.googleapis.com/youtube/v3/search", params={"part": "snippet", "q": "nature", "key": key, "maxResults": 1}, timeout=15)
            if r.status_code == 200:
                return {"ok": True, "message": "YouTube Data API v3 conectada com sucesso!"}
            return {"ok": False, "message": f"YouTube API recusou a chave (código {r.status_code}): {r.text[:200]}"}

        elif key_id == "storyblocks":
            # A API Storyblocks exige APIKEY + EXPIRES + HMAC-SHA256; não usa Bearer.
            secret = os.getenv("STORYBLOCKS_API_SECRET", "").strip()
            if not is_active_key(secret):
                return {"ok": False, "message": "Informe e salve também a Secret Key do Storyblocks antes de testar."}
            import storyblocks_mgr
            try:
                results = storyblocks_mgr.storyblocks_search(
                    "nature", key, "video", 1, "landscape",
                    api_secret=secret, project_id="faceless-connection-test",
                    user_id="faceless-local-user",
                )
                return {"ok": True, "message": f"Storyblocks conectado! Busca de teste retornou {len(results)} resultado(s)."}
            except Exception as exc:
                return {"ok": False, "message": str(exc)[:240]}

        elif key_id == "openrouter":
            r = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "http://localhost:3000", "X-Title": "Faceless Studio"},
                timeout=20,
            )
            if r.status_code == 200:
                return {"ok": True, "message": "OpenRouter conectado! A lista de modelos está acessível."}
            return {"ok": False, "message": f"OpenRouter respondeu HTTP {r.status_code}: {r.text[:180]}"}

        elif key_id == "groq":
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}", "User-Agent": "FacelessCloudStudio/0.4"},
                timeout=15,
            )
            if r.status_code == 200:
                models = [m.get("id", "") for m in r.json().get("data", [])]
                whisper = [m for m in models if "whisper" in m]
                extra = f" Modelos de transcrição: {', '.join(whisper[:2])}." if whisper else ""
                return {"ok": True, "message": f"Conexão com Groq OK!{extra}"}
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message", "")
            except Exception:
                detail = r.text[:200]
            return {"ok": False, "message": f"Groq recusou a chave (código {r.status_code}): {detail}"}

        elif key_id == "app_password":
            return {"ok": True, "message": f"Senha de acesso configurada ({len(key)} caracteres)."}

        return {"ok": False, "message": "Teste não implementado para este serviço."}

    except requests.exceptions.RequestException as exc:
        return {"ok": False, "message": f"Erro de conexão: {str(exc)[:250]}"}
    except Exception as exc:
        return {"ok": False, "message": f"Falha no teste: {str(exc)[:250]}"}
