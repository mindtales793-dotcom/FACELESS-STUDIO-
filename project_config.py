"""Gerenciamento da configuração do projeto (JSON versionado).

Todas as configurações de um projeto ficam num único JSON para reprodutibilidade.
Exemplo (seção 10 da especificação):

{
  "entrada": { "modo": "tema|roteiro|audio|audio_srt" },
  "cenas": { ... },
  "motion_graphics": { ... },
  "avatar": { ... },
  "trilha": { ... },
  "montagem": { ... },
  "thumbnail": { ... },
  "custos": { ... }
}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from store import DATA_DIR, now_iso


DEFAULT_CONFIG: dict[str, Any] = {
    "entrada": {"modo": "tema"},
    "cenas": {
        "fonte": "filmagem_real",
        "modo_busca": "padrao",
        "ritmo": "rapido",
        "prioridade": ["youtube_video", "youtube_clipe", "bancos", "ia"],
        "bancos": ["wikimedia", "nasa", "nara", "openverse", "pexels", "pixabay"],
        "youtube": {"somente_creative_commons": True},
        "ia": {
            "modo": "imagem",
            "modelo_imagem": "gemini-nano-banana-2.1",
            "modelo_video": "gemini-omni-1.2-flash",
            "concorrencia": 3,
            "personagem_referencias": [],
        },
    },
    "motion_graphics": {
        "ativo": False,
        "modo": "equilibrado",
        "percentual": None,
        "estilo": "",
        "subestilo": "",
        "cor": "#2F6FED",
    },
    "avatar": {
        "ativo": False,
        "provedor": "heygen",
        "avatar_id": "",
        "motor": "avatar_iii",
        "frequencia_min": 2,
        "entrada": "auto",
    },
    "trilha": {
        "ativa": False,
        "arquivo": "",
        "nivel": "sutil",
        "ducking": True,
    },
    "montagem": {
        "modo": "parar_se_faltar",
        "cortar_silencios": True,
        "movimento_imagens": True,
        "transicao": "fade",
        "fade_inicio_fim": True,
    },
    "thumbnail": {
        "ativa": False,
        "referencias": [],
        "mostrar_avatar": False,
        "gerador": "nano_banana",
    },
    "flow_agent": {
        "ativo": False,
        "url": "http://localhost:8001",
        "contas_conectadas": 0,
        "ultimo_status": "desconhecido",
    },
    "custos": {"teto_por_video_usd": None},
}


SYSTEM_ID = "sistema"


def system_config_path() -> Path:
    """Configuração global do app (não é um projeto de vídeo).

    Fica em ``data/sistema/config.json``; antes o código usava o id "sistema"
    no mesmo caminho dos projetos, o que estourava 404 em ``project_dir`` e
    deixava a tela do Flow Agent sem conseguir salvar nada.
    """
    folder = DATA_DIR / SYSTEM_ID
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.json"


def load_system_config() -> dict[str, Any]:
    """Lê a configuração global, mesclando com os padrões. Nunca levanta."""
    path = system_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    base = json.loads(json.dumps({"flow_agent": DEFAULT_CONFIG["flow_agent"]}))
    return _deep_merge(base, data)


def update_system_config(patches: dict[str, Any]) -> dict[str, Any]:
    """Aplica patches parciais na configuração global e salva."""
    merged = _deep_merge(load_system_config(), patches)
    data = {**merged, "_atualizado_em": now_iso()}
    system_config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def config_path(project_id: str) -> Path:
    from store import project_dir
    d = project_dir(project_id)
    return d / "config.json"


def load_config(project_id: str) -> dict[str, Any]:
    """Lê a configuração do projeto, mesclando com padrões."""
    path = config_path(project_id)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Mescla recursivamente com DEFAULT_CONFIG para não perder chaves novas
        return _deep_merge(json.loads(json.dumps(DEFAULT_CONFIG)), data)
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(project_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Salva a configuração completa do projeto."""
    path = config_path(project_id)
    data = {
        **config,
        "_atualizado_em": now_iso(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def update_config(project_id: str, patches: dict[str, Any]) -> dict[str, Any]:
    """Aplica patches parciais na configuração do projeto."""
    current = load_config(project_id)
    merged = _deep_merge(current, patches)
    return save_config(project_id, merged)


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
