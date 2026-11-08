"""Integração das Skills da Biblioteca como Estilos de Vídeo para o Editor.

Converte cada SKILL.md da pasta Biblioteca em um estilo de vídeo aplicável nas
cenas, com cor, movimento, transição e efeitos extraídos do conteúdo e da
categoria do skill.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(
    os.getenv(
        "SKILLS_VIDEO_ROOT",
        r"C:\Users\Lucas\Downloads\WebDark-Skills-Alunos-2026-11-03\Biblioteca",
    )
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extrai name e description do cabeçalho --- ... --- de um SKILL.md."""
    data: dict[str, str] = {}
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m:
        block = m.group(1)
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
    return data


def _extrair_cor_texto(text: str) -> str | None:
    """Tenta extrair uma cor hexadecimal do texto do skill."""
    m = re.search(r"#([0-9a-fA-F]{6})", text)
    if m:
        return "#" + m.group(1)
    return None


def _extrair_valor_texto(text: str, palavras: list[str]) -> str | None:
    """Procura por palavras-chave no texto e retorna a primeira encontrada."""
    texto_lower = text.lower()
    for p in palavras:
        if p in texto_lower:
            return p
    return None


def _montar_estilo_por_categoria(categoria: str, texto: str) -> dict[str, Any]:
    """Monta um estilo de vídeo baseado na categoria do skill."""
    cat_lower = categoria.lower()

    # Mapeamento de categoria para estilo base
    mapeamento_categoria = {
        "biografias e documentários": {
            "cor": "#8E44AD", "paleta": "#2C3E50", "motion": "alternate",
            "transicao": "fade", "vignette": 0.3, "grain": 5,
        },
        "bíblia": {
            "cor": "#D4AF37", "paleta": "#1A1A2E", "motion": "alternate",
            "transicao": "crossfade", "vignette": 0.35, "grain": 3,
        },
        "educação e ciência": {
            "cor": "#00D2FF", "paleta": "#0F172A", "motion": "zoom_in",
            "transicao": "slideleft", "vignette": 0.15, "grain": 2,
        },
        "estrutura e revisão": {
            "cor": "#F59E0B", "paleta": "#1E293B", "motion": "pan_right",
            "transicao": "slideup", "vignette": 0.25, "grain": 3,
        },
        "finanças": {
            "cor": "#10B981", "paleta": "#0F2A2A", "motion": "zoom_out",
            "transicao": "fadeblack", "vignette": 0.4, "grain": 2,
        },
        "história antiga": {
            "cor": "#C19A6B", "paleta": "#2D1B1B", "motion": "drift",
            "transicao": "crossfade", "vignette": 0.45, "grain": 8,
        },
        "histórias emocionantes": {
            "cor": "#EF4444", "paleta": "#1F1515", "motion": "punch_in",
            "transicao": "fadewhite", "vignette": 0.5, "grain": 10,
        },
        "mistério e suspense": {
            "cor": "#6366F1", "paleta": "#0B0C10", "motion": "handheld",
            "transicao": "fadeblack", "vignette": 0.6, "grain": 12,
        },
        "negócios e empreendedorismo": {
            "cor": "#22C55E", "paleta": "#0F172A", "motion": "zoom_in",
            "transicao": "slideleft", "vignette": 0.2, "grain": 2,
        },
        "visual": {
            "cor": "#06B6D4", "paleta": "#0B0C10", "motion": "handheld",
            "transicao": "slideleft", "vignette": 0.2, "grain": 5,
        },
        "câmera": {
            "cor": "#F59E0B", "paleta": "#1E293B", "motion": "zoom_in",
            "transicao": "crossfade", "vignette": 0.15, "grain": 5,
        },
        "som": {
            "cor": "#10B981", "paleta": "#0F2A2A", "motion": "none",
            "transicao": "fade", "vignette": 0.1, "grain": 0,
        },
        "edição": {
            "cor": "#EF4444", "paleta": "#1F1515", "motion": "punch_in",
            "transicao": "flash", "vignette": 0.3, "grain": 5,
        },
        "thumbnails": {
            "cor": "#E91E63", "paleta": "#1E1E1E", "motion": "none",
            "transicao": "fadewhite", "vignette": 0.1, "grain": 0,
        },
    }

    cfg = mapeamento_categoria.get(
        cat_lower,
        {"cor": "#6366F1", "paleta": "#0F172A", "motion": "none",
         "transicao": "cut", "vignette": 0.2, "grain": 0},
    )

    # Tenta extrair cor real do texto
    cor_extraida = _extrair_cor_texto(texto)
    cor = cor_extraida if cor_extraida else cfg["cor"]

    # Tenta extrair movimento do texto
    motion = cfg["motion"]
    palavra_motion = _extrair_valor_texto(texto, list(MOTION_KEYWORDS.keys()))
    if palavra_motion:
        motion = palavra_motion

    # Tenta extrair transição do texto
    transicao = cfg["transicao"]
    palavra_transicao = _extrair_valor_texto(texto, list(TRANSICAO_KEYWORDS.keys()))
    if palavra_transicao:
        transicao = palavra_transicao

    # Efeitos baseados no texto
    efeitos: dict[str, float | bool] = {}
    for efeito, palavras in EFEITO_KEYWORDS.items():
        if _extrair_valor_texto(texto, palavras):
            efeitos[efeito] = True if efeito == "mirror" else 0.15

    estilo = {
        "grade": {"contrast": 1.05, "saturation": 1.1, "brightness": 0.0,
                  "gamma": 1.0, "mono": False, "sepia": False},
        "vignette": cfg["vignette"],
        "grain": cfg["grain"],
        "letterbox": False,
        "motion": motion,
        "motion_strength": 0.10,
        "motion_video": False,
        "transition": transicao,
        "transition_dur": 0.40,
        "effects": efeitos if efeitos else {
            "chroma": 0.0, "glitch": 0.0, "scanlines": 0.0, "shake": 0.0,
            "flicker": 0.0, "sharpen": 0.0, "soft": 0.0, "pixel": 0.0,
            "mirror": False,
        },
        "overlays": {"verse_cards": False, "callouts": False,
                     "topic_bar": False},
        "cta": {"enabled": False, "position": "end", "anchor": "top",
                "language": "auto", "style": "red", "seconds": 5.0, "text": ""},
        "subtitles": {"enabled": True, "mode": "block", "font": "Poppins",
                      "bold": True, "size": 0.045, "color": "#FFFFFF",
                      "outline_color": "#000000", "outline": 0.09,
                      "shadow": 0.03, "box": False, "box_opacity": 0.55,
                      "position": "bottom", "uppercase": False,
                      "highlight": "#FFD60A", "words": 3, "animation": "fade"},
        "cor_primaria": cor,
        "paleta": cfg["paleta"],
    }

    return estilo


# Palavras-chave para detecção automática
MOTION_KEYWORDS = {
    "zoom_in": ["zoom in", "aproximar", "zoom"],
    "zoom_out": ["zoom out", "afastar"],
    "pan_left": ["pan left", "esquerda"],
    "pan_right": ["pan right", "direita"],
    "pan_up": ["pan up", "cima"],
    "pan_down": ["pan down", "baixo"],
    "drift": ["drift", "deslizar"],
    "alternate": ["alternate", "alternar"],
    "handheld": ["handheld", "mão", "tremor"],
    "orbit": ["orbit", "órbita", "círculo"],
    "diagonal_in": ["diagonal_in", "diagonal in"],
    "diagonal_out": ["diagonal_out", "diagonal out"],
    "punch_in": ["punch_in", "punch in", "impacto"],
}

TRANSICAO_KEYWORDS = {
    "crossfade": ["crossfade", "dissolver", "transição suave"],
    "fadeblack": ["fade black", "fade preto", "escurecer"],
    "fadewhite": ["fade white", "branco", "claro"],
    "slideleft": ["slide left", "deslizar esquerda"],
    "slideright": ["slide right", "deslizar direita"],
    "slideup": ["slide up", "deslizar cima"],
    "slidedown": ["slide down", "deslizar baixo"],
    "smoothleft": ["smooth left", "suave esquerda"],
    "wipeleft": ["wipe left", "limpar esquerda"],
    "wiperight": ["wipe right", "limpar direita"],
    "circleopen": ["circle", "íris", "círculo"],
    "radial": ["radial", "relógio"],
    "pixelize": ["pixel", "pixelize"],
    "dissolve": ["dissolve", "dissolver"],
    "zoomin": ["zoomin", "zoom through"],
    "hlslice": ["hlslice", "persiana horizontal"],
    "vuslice": ["vuslice", "persiana vertical"],
    "diagtl": ["diagtl", "fatias diagonais"],
    "squeezeh": ["squeezeh", "compressão horizontal"],
    "hblur": ["hblur", "desfoque de passagem"],
    "fadegrays": ["fadegrays", "cortina de cinza"],
}

EFEITO_KEYWORDS = {
    "chroma": ["chroma", "aberração"],
    "glitch": ["glitch"],
    "scanlines": ["scanlines", "varredura"],
    "shake": ["shake", "tremor"],
    "flicker": ["flicker", "piscar"],
    "sharpen": ["sharpen", "nitidez"],
    "soft": ["soft", "suave"],
    "pixel": ["pixel", "retrô"],
    "mirror": ["mirror", "espelhar"],
}


def load_skills_estilo() -> list[dict[str, Any]]:
    """Carrega todas as skills e converte em estilos de vídeo aplicáveis."""
    estilos: list[dict[str, Any]] = []
    if not SKILLS_ROOT.exists():
        return estilos

    for skill_md in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        skill_dir = skill_md.parent

        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Extrai name e description do frontmatter
        m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        name = skill_dir.name
        descricao = ""
        if m:
            block = m.group(1)
            for line in block.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    descricao = line.split(":", 1)[1].strip()

        estilo = _montar_estilo_por_categoria(skill_dir.parent.name, text)

        estilos.append({
            "id": skill_dir.name,
            "name": name,
            "descricao": descricao,
            "categoria": skill_dir.parent.name,
            "pasta": skill_dir.name,
            "caminho": str(skill_dir),
            "estilo": estilo,
            "tem_metodo": (skill_dir / "method.md").exists(),
            "tem_roteiro": any(
                f.suffix.lower() in (".txt", ".md")
                for f in (skill_dir / "scripts").iterdir()
            ) if (skill_dir / "scripts").exists() else False,
        })

    return estilos


def get_estilo_skill(skill_id: str) -> dict[str, Any] | None:
    """Retorna o estilo de vídeo de uma skill específica."""
    for s in load_skills_estilo():
        if s["id"] == skill_id:
            return s
    return None
