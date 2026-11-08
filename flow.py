"""Geração com IA pelos mesmos modelos do Google Flow: Veo (vídeo) e Nano Banana (imagem).

O Google Flow não tem API pública. Existem dois caminhos:
  1. Servidores MCP "Google Flow" da comunidade que automatizam o site do Flow num Chrome logado
     (usam a sua conta e o seu plano do Flow, mas dependem do layout do site e quebram quando ele muda).
  2. A Gemini API, que dá acesso aos mesmos modelos (Veo e Nano Banana) por chamada oficial.
Este módulo usa o caminho 2: é estável e roda no servidor sem navegador. Os clipes não aparecem no seu
projeto do Flow e são cobrados na chave da Gemini API (o Veo não tem camada gratuita).
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Callable

import requests

import flow_agent_client
from keys_mgr import is_active_key
from store import DATA_DIR, BASE_DIR

FLOW_GALLERY_DIR = DATA_DIR / "flow_gallery"
FLOW_GALLERY_DIR.mkdir(parents=True, exist_ok=True)
MCP_OUT_DIR = DATA_DIR / "mcp_outputs"
MCP_OUT_DIR.mkdir(parents=True, exist_ok=True)

API = "https://generativelanguage.googleapis.com/v1beta"
IMAGE_MODEL = os.getenv("FLOW_IMAGE_MODEL", "gemini-2.5-flash-image")
VIDEO_MODEL = os.getenv("FLOW_VIDEO_MODEL", "veo-3.1-fast-generate-preview")


def api_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not is_active_key(key):
        raise RuntimeError("Configure GEMINI_API_KEY na tela de Chaves para gerar mídia com IA (Veo e Nano Banana).")
    return key


def _gemini_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def is_ready() -> bool:
    """Há um motor pronto: o Flow Agent local ou a Gemini API com chave."""
    if flow_agent_client.enabled():
        return flow_agent_client.health() is not None
    return is_active_key(_gemini_key())


def readiness_error() -> str:
    """Mensagem que explica por que a geração ainda não está liberada."""
    if flow_agent_client.enabled():
        return (
            "O Flow Agent está ativado, mas o servidor não respondeu em "
            f"{flow_agent_client.base_url()}. Inicie o servidor do flow-agent "
            "(python main.py server) e use 'Testar conexão' na aba Chaves de API."
        )
    return (
        "Configure GEMINI_API_KEY na tela de Chaves ou ative o Flow Agent "
        "(servidor local do flow-agent) em Chaves de API."
    )


def _headers() -> dict[str, str]:
    return {"x-goog-api-key": api_key(), "Content-Type": "application/json"}


def _explain(response: requests.Response, model: str) -> str:
    try:
        detail = response.json().get("error", {}).get("message") or response.text[:300]
    except Exception:
        detail = response.text[:300]
    code = response.status_code
    if code == 429:
        return "Cota esgotada ou faturamento desativado na Gemini API. O Veo não tem camada gratuita: ative o faturamento no Google AI Studio."
    if code == 404:
        return f"O modelo «{model}» não está disponível para a sua chave. Veja os modelos liberados em Fontes e ajuste FLOW_VIDEO_MODEL ou FLOW_IMAGE_MODEL."
    if code in (400, 403):
        return f"O Google recusou o pedido ({code}): {detail}"
    return f"A Gemini API respondeu {code}: {detail}"


def list_models() -> list[dict[str, str]]:
    if flow_agent_client.enabled():
        return [
            {"id": "narwhal", "title": "Nano Banana (Flow Agent)", "kind": "image"},
            {"id": "harbor_seal", "title": "Imagem alternativa (Flow Agent)", "kind": "image"},
            {"id": "veo", "title": "Veo (Flow Agent)", "kind": "video"},
        ]
    response = requests.get(f"{API}/models", headers=_headers(), params={"pageSize": 200}, timeout=30)
    if not response.ok:
        raise RuntimeError(_explain(response, "lista de modelos"))
    out = []
    for m in response.json().get("models", []):
        name = str(m.get("name", "")).replace("models/", "")
        if "veo" in name or "image" in name or "imagen" in name:
            out.append({"id": name, "title": m.get("displayName", name), "kind": "video" if "veo" in name else "image"})
    return out


def generate_image(prompt: str, ratio: str, dest: Path, model: str | None = None, reference_image: str | None = None) -> Path:
    if flow_agent_client.enabled():
        return flow_agent_client.generate_image(prompt, ratio, dest, model=model, reference_image=reference_image)
    if reference_image:
        return generate_image_with_ref(prompt, ratio, dest, reference_image)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio if ratio in ("16:9", "9:16", "1:1") else "16:9"}},
    }
    response = requests.post(f"{API}/models/{IMAGE_MODEL}:generateContent", headers=_headers(), json=body, timeout=(20, 180))
    if not response.ok:
        raise RuntimeError(_explain(response, IMAGE_MODEL))
    data = response.json()
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                dest = dest.with_suffix(".png")
                dest.write_bytes(base64.b64decode(inline["data"]))
                return dest
    reason = (data.get("promptFeedback") or {}).get("blockReason") or "sem imagem na resposta"
    raise RuntimeError(f"O Google não devolveu a imagem ({reason}). Reescreva o prompt.")


def generate_video(prompt: str, ratio: str, seconds: int, dest: Path, on_status: Callable[[str], None] | None = None,
                   cancel: Callable[[], bool] | None = None, timeout: int = 900, model: str | None = None) -> Path:
    if flow_agent_client.enabled():
        if on_status:
            on_status("Flow Agent gerando... isso pode levar alguns minutos.")
        return flow_agent_client.generate_video(prompt, ratio, seconds, dest, model=model)
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {"aspectRatio": "9:16" if ratio == "9:16" else "16:9", "durationSeconds": seconds},
    }
    response = requests.post(f"{API}/models/{VIDEO_MODEL}:predictLongRunning", headers=_headers(), json=body, timeout=(20, 90))
    if not response.ok:
        raise RuntimeError(_explain(response, VIDEO_MODEL))
    op_name = response.json().get("name")
    if not op_name:
        raise RuntimeError("O Google não devolveu o identificador da geração.")
    start = time.monotonic()
    while True:
        if cancel and cancel():
            raise RuntimeError("Geração cancelada.")
        if time.monotonic() - start > timeout:
            raise RuntimeError("O Veo demorou mais de 15 minutos. Tente de novo ou use um prompt mais simples.")
        time.sleep(8)
        poll = requests.get(f"{API}/{op_name}", headers=_headers(), timeout=45)
        if not poll.ok:
            raise RuntimeError(_explain(poll, VIDEO_MODEL))
        op = poll.json()
        if on_status:
            on_status(f"Veo gerando... {int(time.monotonic() - start)} s")
        if not op.get("done"):
            continue
        if op.get("error"):
            raise RuntimeError(f"O Veo falhou: {op['error'].get('message', 'erro desconhecido')}")
        resp = op.get("response", {})
        gen = resp.get("generateVideoResponse", resp)
        filtered = gen.get("raiMediaFilteredReasons")
        if filtered:
            raise RuntimeError(f"O filtro de segurança do Google bloqueou o vídeo: {'; '.join(map(str, filtered))[:200]}")
        samples = gen.get("generatedSamples") or gen.get("videos") or []
        uri = ((samples[0].get("video") or samples[0]) if samples else {}).get("uri")
        if not uri:
            raise RuntimeError("A geração terminou, mas o Google não devolveu o arquivo de vídeo.")
        dest = dest.with_suffix(".mp4")
        with requests.get(uri, headers={"x-goog-api-key": api_key()}, stream=True, timeout=(20, 180), allow_redirects=True) as dl:
            if not dl.ok:
                raise RuntimeError(_explain(dl, VIDEO_MODEL))
            with dest.open("wb") as handle:
                for chunk in dl.iter_content(chunk_size=1024 * 1024):
                    handle.write(chunk)
        if dest.stat().st_size < 1000:
            raise RuntimeError("O arquivo de vídeo baixado está vazio.")
        return dest


def generate_prompts_from_script(script: str, max_blocks: int = 20) -> list[dict[str, str]]:
    """Divide um roteiro em blocos e sugere um prompt de imagem para cada um.

    Devolve [{'id': ..., 'texto': ..., 'prompt': ...}] prontos para gerar via Nano Banana.
    """
    import re as _re
    # Limpa o roteiro
    texto = str(script or "").strip()
    if not texto:
        return []
    # Divide em blocos por parágrafos ou quebras duplas
    blocos_raw = [b.strip() for b in _re.split(r"\n\s*\n", texto) if b.strip()]
    # Se não houver quebras de parágrafo, divide por sentenças longas
    if len(blocos_raw) < 2:
        partes = _re.split(r"(?<=[.!?])\s+", texto)
        blocos_raw = []
        atual = ""
        for parte in partes:
            if len(atual) + len(parte) > 200 and atual:
                blocos_raw.append(atual.strip())
                atual = parte
            else:
                atual = (atual + " " + parte).strip()
        if atual.strip():
            blocos_raw.append(atual.strip())
    # Limita o número de blocos
    blocos_raw = blocos_raw[:max_blocks]

    # Usa a Gemini API para refinar/gerar prompts de imagem para cada bloco
    chave = flow_api_key()
    if not chave:
        # Sem chave: devolve prompts simples baseados no texto do bloco
        return [{"id": f"bloco_{i}", "texto": b, "prompt": f"Illustration, 2D animation style, {b[:200]}" } for i, b in enumerate(blocos_raw)]

    api = "https://generativelanguage.googleapis.com/v1beta"
    headers = {"x-goog-api-key": chave, "Content-Type": "application/json"}
    resultados = []
    for i, bloco in enumerate(blocos_raw):
        instrucao = (
            "Você é um diretor de arte de animação 2D. "
            "Leia este trecho de roteiro e escreva UM prompt curto em inglês para gerar uma imagem "
            "no estilo anime/animação 2D, cena única, sem personagem repetido entre blocos. "
            "Descreva apenas o que deve aparecer na imagem (cenário, personagem, ação, iluminação, cores). "
            "Não inclua nada além do prompt em inglês. Máximo 80 palavras.\n\nTrecho: "
            + bloco[:800]
        )
        corpo = {"contents": [{"parts": [{"text": instrucao}]}], "generationConfig": {"temperature": 0.7}}
        try:
            resp = requests.post(f"{api}/models/{IMAGE_MODEL}:generateContent", headers=headers, json=corpo, timeout=(20, 60))
            if resp.ok:
                dados = resp.json()
                partes = ((dados.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                prompt_gerado = ""
                for parte in partes:
                    if parte.get("text"):
                        prompt_gerado = parte["text"].strip()
                        break
                if not prompt_gerado:
                    prompt_gerado = f"Illustration, 2D animation style, {bloco[:200]}"
            else:
                prompt_gerado = f"Illustration, 2D animation style, {bloco[:200]}"
        except Exception:
            prompt_gerado = f"Illustration, 2D animation style, {bloco[:200]}"
        resultados.append({"id": f"bloco_{i}", "texto": bloco, "prompt": prompt_gerado})
    return resultados


def blocks_from_srt(srt_text: str, max_blocks: int = 60) -> list[dict[str, Any]]:
    """Extrai blocos de um arquivo SRT e gera um prompt de imagem para cada um."""
    from scenes import parse_srt
    cues = parse_srt(srt_text)
    cues = cues[:max_blocks]
    resultados = []
    chave = flow_api_key()
    for i, cue in enumerate(cues):
        texto = str(cue.get("text", ""))
        prompt = ""
        if chave:
            import requests as _req
            api = "https://generativelanguage.googleapis.com/v1beta"
            headers = {"x-goog-api-key": chave, "Content-Type": "application/json"}
            instrucao = (
                "Você é um diretor de arte de animação 2D. "
                "Leia este trecho de legendas com tempo e escreva UM prompt curto em inglês para gerar uma imagem "
                "ou quadro de animação 2D (estilo anime). Descreva cenário, personagem, ação, iluminação e cores. "
                "Não inclua nada além do prompt em inglês. Máximo 80 palavras.\n\nTrecho: "
                + texto[:500]
            )
            corpo = {"contents": [{"parts": [{"text": instrucao}]}], "generationConfig": {"temperature": 0.7}}
            try:
                resp = _req.post(f"{api}/models/{IMAGE_MODEL}:generateContent", headers=headers, json=corpo, timeout=(20, 60))
                if resp.ok:
                    dados = resp.json()
                    partes = ((dados.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                    for parte in partes:
                        if parte.get("text"):
                            prompt = parte["text"].strip()
                            break
            except Exception:
                pass
        if not prompt:
            prompt = f"Illustration, 2D animation style, {texto[:200]}"
        resultados.append({
            "id": f"srt_bloco_{i}",
            "texto": texto,
            "prompt": prompt,
            "start": float(cue.get("start", 0)),
            "end": float(cue.get("end", 0)),
        })
    return resultados


def generate_image_with_ref(prompt: str, ratio: str, dest: Path, reference_image: str | None = None) -> Path:
    """Gera imagem via Nano Banana, opcionalmente com imagem de referência."""
    if flow_agent_client.enabled():
        return flow_agent_client.generate_image(prompt, ratio, dest, reference_image=reference_image)
    if reference_image:
        return flow_agent_client.upload_reference(reference_image) and generate_image_with_ref(prompt, ratio, dest, None)
    import base64 as _b64
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if reference_image:
        try:
            ref_path = Path(reference_image)
            if ref_path.exists():
                data = ref_path.read_bytes()
                mime = "image/png"
                if ref_path.suffix.lower() in (".jpg", ".jpeg"):
                    mime = "image/jpeg"
                elif ref_path.suffix.lower() == ".webp":
                    mime = "image/webp"
                parts.insert(0, {"inlineData": {"mimeType": mime, "data": _b64.b64encode(data).decode()}})
        except Exception:
            pass
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio if ratio in ("16:9", "9:16", "1:1") else "16:9"}},
    }
    response = requests.post(f"{API}/models/{IMAGE_MODEL}:generateContent", headers=_headers(), json=body, timeout=(20, 180))
    if not response.ok:
        raise RuntimeError(_explain(response, IMAGE_MODEL))
    data = response.json()
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                dest = dest.with_suffix(".png")
                dest.write_bytes(_b64.b64decode(inline["data"]))
                return dest
    reason = (data.get("promptFeedback") or {}).get("blockReason") or "sem imagem na resposta"
    raise RuntimeError(f"O Google não devolveu a imagem ({reason}). Reescreva o prompt.")


def generate_block_video(prompt: str, ratio: str, seconds: int, dest: Path) -> Path:
    """Gera um clipe de vídeo para um bloco via Veo."""
    return generate_video(prompt, ratio, seconds, dest)


def upload_reference(file_path: str) -> str:
    """Envia uma imagem de referência para o servidor do Flow Agent."""
    return flow_agent_client.upload_reference(file_path)


def flow_api_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not is_active_key(key):
        return ""
    return key


def list_gallery_items() -> list[dict[str, Any]]:
    """Lista as mídias geradas na aba Flow e pelo servidor MCP."""
    items: list[dict[str, Any]] = []
    seen = set()

    for folder in (FLOW_GALLERY_DIR, MCP_OUT_DIR):
        if not folder.exists():
            continue
        for p in folder.iterdir():
            if not p.is_file() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"):
                continue
            if p.name in seen:
                continue
            seen.add(p.name)

            stat = p.stat()
            meta_file = p.with_suffix(p.suffix + ".json")
            prompt = ""
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    prompt = meta.get("prompt", "")
                except Exception:
                    pass

            is_video = p.suffix.lower() in (".mp4", ".mov")
            items.append({
                "filename": p.name,
                "url": f"/api/flow/gallery/{p.name}",
                "kind": "video" if is_video else "image",
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "prompt": prompt,
            })

    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items


def get_mcp_config() -> dict[str, Any]:
    """Retorna a configuração JSON pronta para Claude Desktop / Claude Code."""
    python_exe = os.sys.executable
    mcp_script = str((BASE_DIR / "mcp_server.py").resolve())
    return {
        "mcpServers": {
            "faceless-studio": {
                "command": python_exe,
                "args": [mcp_script],
                "env": {
                    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
                    "DATA_DIR": str(DATA_DIR),
                },
            }
        }
    }

