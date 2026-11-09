"""Motion Graphics com Remotion — 3 modos: equilibrado, cheio, identidade.

Cada cena animada é uma composição Remotion que recebe props em JSON.
Estilos e subestilos definem paleta, tipografia e regras de movimento.
Renderização em worker com cache por hash das props.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from store import DATA_DIR, now_iso

MOTION_DIR = DATA_DIR / "motion_graphics"
MOTION_DIR.mkdir(parents=True, exist_ok=True)

# Estilos e subestilos (extensível — arquivo/pasta por estilo)
ESTILOS: dict[str, dict[str, Any]] = {
    "cinema_dark": {
        "label": "Cinema Dark",
        "paleta": "#0B0F19",
        "cor": "#2F6FED",
        "tipografia": "Cinzel, serif",
        "subestilos": {
            "sobrio": {"label": "Sóbrio", "movimento": "suave", "tipo_cenas": ["texto", "contador", "linha_tempo"]},
            "epico": {"label": "Épico", "movimento": "intenso", "tipo_cenas": ["texto", "mapa", "icone", "destaque"]},
        },
    },
    "neon_cyber": {
        "label": "Neon Cyber",
        "paleta": "#050505",
        "cor": "#00F2FF",
        "tipografia": "Orbitron, sans-serif",
        "subestilos": {
            "glitch": {"label": "Glitch", "movimento": "treme", "tipo_cenas": ["texto", "destaque", "icone"]},
            "clean": {"label": "Limpo", "movimento": "fluido", "tipo_cenas": ["texto", "linha_tempo", "mapa"]},
        },
    },
    "minimal": {
        "label": "Minimalista",
        "paleta": "#FFFFFF",
        "cor": "#000000",
        "tipografia": "Inter, sans-serif",
        "subestilos": {
            "leve": {"label": "Leve", "movimento": "minimo", "tipo_cenas": ["texto", "contador"]},
        },
    },
}


def estilo_lista() -> list[dict[str, Any]]:
    """Devolve estilos com subestilos para a UI."""
    out = []
    for estilo_id, estilo in ESTILOS.items():
        out.append({
            "id": estilo_id,
            "label": estilo["label"],
            "paleta": estilo["paleta"],
            "cor": estilo["cor"],
            "tipografia": estilo["tipografia"],
            "subestilos": [
                {"id": sub_id, "label": sub["label"], "movimento": sub["movimento"],
                 "tipo_cenas": sub["tipo_cenas"]}
                for sub_id, sub in estilo["subestilos"].items()
            ],
        })
    return out


def percentual_por_modo(modo: str, percentual: int | None = None) -> int:
    """Devolve o percentual de animação para cada modo."""
    tabelas = {
        "equilibrado": 25,
        "cheio": 60,
        "identidade": 90,
    }
    if percentual is not None:
        return max(0, min(100, percentual))
    return tabelas.get(modo, 25)


def hash_props(props: dict[str, Any]) -> str:
    """Cache key por hash das props."""
    return hashlib.sha256(json.dumps(props, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def render_composicao(tipo_cena: str, props: dict[str, Any], estilo_id: str,
                      subestilo_id: str | None, cor: str, duracao_s: float) -> dict[str, Any]:
    """Renderiza uma composição Remotion (placeholder — integração real com @remotion/renderer).

    Devolve {url, path, tipo_cena, estilo, duracao_s, cache_hit}.
    """
    chave = hash_props({"tipo": tipo_cena, "props": props, "estilo": estilo_id,
                        "subestilo": subestilo_id, "cor": cor, "duracao": duracao_s})
    out_path = MOTION_DIR / f"{chave}.mp4"
    meta_path = MOTION_DIR / f"{chave}.json"

    if out_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return {"url": f"/api/motion/{chave}.mp4", "path": str(out_path),
                "cache_hit": True, "duracao_s": duracao_s}

    # Placeholder: grava um vídeo de cor sólida com FFmpeg (substituído pelo Remotion real)
    import subprocess
    from store import ffmpeg_path
    largura, altura = 1920, 1080
    cmd = [
        ffmpeg_path(), "-y", "-f", "lavfi", "-i",
        f"color=c={cor.replace('#', '0x')}:s={largura}x{altura}:r=24:d={duracao_s}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(duracao_s), str(out_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception:
        pass

    meta = {"tipo_cena": tipo_cena, "estilo": estilo_id, "subestilo": subestilo_id,
            "cor": cor, "duracao_s": duracao_s, "criado_em": now_iso()}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"url": f"/api/motion/{chave}.mp4", "path": str(out_path),
            "cache_hit": False, "duracao_s": duracao_s}


def tempo_estimado_por_modo(modo: str, num_cenas: int) -> dict[str, Any]:
    """Estima tempo de render por modo (referência: +10 a 20 min no modo identidade)."""
    minutos_por_cena = {"equilibrado": 2, "cheio": 5, "identidade": 12}
    mp = minutos_por_cena.get(modo, 2)
    total_min = num_cenas * mp
    return {"modo": modo, "num_cenas": num_cenas, "min_estimado": total_min,
            "texto": f"~{total_min} min para {num_cenas} cenas no modo {modo}."}
