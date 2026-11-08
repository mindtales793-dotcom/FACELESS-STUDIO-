"""Templates de estilo de vídeo: grade de cor, movimento, transições e legendas (ASS).

Tudo é aplicado pelo FFmpeg no servidor. Cada template é um conjunto de valores que pode
ser ajustado depois (legenda, movimento, transição, vinheta, granulação, faixas de cinema).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from store import PREVIEW_DIR, BASE_DIR, ffmpeg_path, run_ffmpeg

FONTS_DIR = BASE_DIR / "static" / "fonts"

FONT_CHOICES = [
    {"family": "Poppins", "bold": True, "label": "Poppins Bold", "css": "Poppins"},
    {"family": "Anton", "bold": False, "label": "Anton", "css": "Anton"},
    {"family": "Bebas Neue", "bold": False, "label": "Bebas Neue", "css": "Bebas Neue"},
    {"family": "Archivo Black", "bold": False, "label": "Archivo Black", "css": "Archivo Black"},
    {"family": "DM Serif Display", "bold": False, "label": "DM Serif Display", "css": "DM Serif Display"},
    {"family": "Cinzel", "bold": True, "label": "Cinzel", "css": "Cinzel"},
    {"family": "EB Garamond", "bold": False, "label": "EB Garamond", "css": "EB Garamond"},
]
FONT_FAMILIES = {f["family"]: f for f in FONT_CHOICES}

# ------------------------------------------------------------------ catálogo de movimento, transição e efeitos
# Inspirado em bibliotecas abertas pesquisadas no GitHub (remotion-templates,
# editly, CapRocket) e nas transições nativas do filtro xfade do FFmpeg.
# O catálogo é exposto em /api/catalog para a interface montar os menus.

MOTIONS: dict[str, dict[str, str]] = {
    "none": {"label": "Parado", "hint": "Sem movimento de câmera."},
    "zoom_in": {"label": "Zoom lento para dentro", "hint": "Aproxima devagar, estilo Ken Burns."},
    "zoom_out": {"label": "Zoom lento para fora", "hint": "Começa perto e afasta."},
    "alternate": {"label": "Alternar dentro e fora", "hint": "Alterna o sentido a cada cena."},
    "drift": {"label": "Deslizar para o lado", "hint": "Deslocamento lateral suave."},
    "pan_left": {"label": "Panorâmica para a esquerda", "hint": "A câmera caminha para a esquerda."},
    "pan_right": {"label": "Panorâmica para a direita", "hint": "A câmera caminha para a direita."},
    "pan_up": {"label": "Panorâmica para cima", "hint": "Sobe devagar pela imagem."},
    "pan_down": {"label": "Panorâmica para baixo", "hint": "Desce devagar pela imagem."},
    "diagonal_in": {"label": "Diagonal aproximando", "hint": "Zoom com deslocamento diagonal."},
    "diagonal_out": {"label": "Diagonal afastando", "hint": "Afasta com deslocamento diagonal."},
    "punch_in": {"label": "Punch-in de impacto", "hint": "Aproximação acelerada para Shorts."},
    "handheld": {"label": "Câmera na mão", "hint": "Tremor sutil de documentário."},
    "orbit": {"label": "Órbita suave", "hint": "Percorre a imagem em círculo."},
}

TRANSITIONS: dict[str, dict[str, Any]] = {
    "cut": {"label": "Corte seco", "mode": "cut", "xfade": None},
    "fade": {"label": "Escurecer (fade clássico)", "mode": "dip", "xfade": None},
    "flash": {"label": "Flash branco (clássico)", "mode": "dip", "xfade": None},
    "crossfade": {"label": "Dissolver (crossfade)", "mode": "xfade", "xfade": "fade"},
    "fadeblack": {"label": "Fade para preto", "mode": "xfade", "xfade": "fadeblack"},
    "fadewhite": {"label": "Flash branco suave", "mode": "xfade", "xfade": "fadewhite"},
    "slideleft": {"label": "Deslizar para a esquerda", "mode": "xfade", "xfade": "slideleft"},
    "slideright": {"label": "Deslizar para a direita", "mode": "xfade", "xfade": "slideright"},
    "slideup": {"label": "Deslizar para cima", "mode": "xfade", "xfade": "slideup"},
    "slidedown": {"label": "Deslizar para baixo", "mode": "xfade", "xfade": "slidedown"},
    "smoothleft": {"label": "Empurrão suave", "mode": "xfade", "xfade": "smoothleft"},
    "wipeleft": {"label": "Limpar para a esquerda", "mode": "xfade", "xfade": "wipeleft"},
    "wiperight": {"label": "Limpar para a direita", "mode": "xfade", "xfade": "wiperight"},
    "circleopen": {"label": "Íris circular", "mode": "xfade", "xfade": "circleopen"},
    "radial": {"label": "Relógio radial", "mode": "xfade", "xfade": "radial"},
    "pixelize": {"label": "Pixel dissolve", "mode": "xfade", "xfade": "pixelize"},
    "dissolve": {"label": "Dissolver granulado", "mode": "xfade", "xfade": "dissolve"},
    "zoomin": {"label": "Zoom through", "mode": "xfade", "xfade": "zoomin"},
    "hlslice": {"label": "Persianas horizontais", "mode": "xfade", "xfade": "hlslice"},
    "vuslice": {"label": "Persianas verticais", "mode": "xfade", "xfade": "vuslice"},
    "diagtl": {"label": "Fatias diagonais", "mode": "xfade", "xfade": "diagtl"},
    "squeezeh": {"label": "Compressão horizontal", "mode": "xfade", "xfade": "squeezeh"},
    "hblur": {"label": "Desfoque de passagem", "mode": "xfade", "xfade": "hblur"},
    "fadegrays": {"label": "Cortina de cinza", "mode": "xfade", "xfade": "fadegrays"},
}

EFFECTS: dict[str, dict[str, str]] = {
    "chroma": {"label": "Aberração cromática", "hint": "Separa levemente o vermelho e o azul, estilo lente antiga."},
    "glitch": {"label": "Glitch digital", "hint": "Deslocamento de cor e ruído temporal."},
    "scanlines": {"label": "Linhas de varredura", "hint": "Textura de monitor/VHS."},
    "shake": {"label": "Tremor de câmera", "hint": "Microtremor em toda a cena."},
    "flicker": {"label": "Flicker de luz", "hint": "Variação sutil de brilho, como projetor antigo."},
    "sharpen": {"label": "Nitidez", "hint": "Realça detalhes e texturas."},
    "soft": {"label": "Suavização", "hint": "Deixa a imagem mais sonhadora."},
    "pixel": {"label": "Pixelização", "hint": "Estética retrô/digital."},
    "mirror": {"label": "Espelhar", "hint": "Inverte a imagem horizontalmente."},
}

CTA_STYLES: dict[str, dict[str, Any]] = {
    "red": {"label": "Vermelho", "back": "#E11D2E", "text": "#FFFFFF", "sub": "#FFE4E6", "accent": "#FFFFFF", "alpha": 0.94},
    "gold": {"label": "Dourado", "back": "#7C4A08", "text": "#FEF3C7", "sub": "#FDE68A", "accent": "#F59E0B", "alpha": 0.92},
    "neon": {"label": "Neon", "back": "#083344", "text": "#ECFEFF", "sub": "#67E8F9", "accent": "#22D3EE", "alpha": 0.90},
    "minimal": {"label": "Minimalista", "back": "#0F172A", "text": "#FFFFFF", "sub": "#CBD5E1", "accent": "#94A3B8", "alpha": 0.86},
    "dark": {"label": "Escuro e amarelo", "back": "#000000", "text": "#FFD60A", "sub": "#FDE68A", "accent": "#FFD60A", "alpha": 0.86},
    "white": {"label": "Branco", "back": "#FFFFFF", "text": "#111827", "sub": "#374151", "accent": "#E11D2E", "alpha": 0.95},
}

CTA_TEXTS: dict[str, tuple[str, str]] = {
    "pt": ("SE INSCREVA NO CANAL", "e ative o sininho"),
    "en": ("SUBSCRIBE TO THE CHANNEL", "and turn on notifications"),
    "es": ("SUSCRÍBETE AL CANAL", "y activa la campana"),
}

BASE_STYLE: dict[str, Any] = {
    "grade": {"contrast": 1.0, "saturation": 1.0, "brightness": 0.0, "gamma": 1.0, "mono": False, "sepia": False, "balance": None, "curve": None},
    "vignette": 0.0,
    "grain": 0,
    "letterbox": False,
    "motion": "none",            # ver MOTIONS
    "motion_strength": 0.10,
    "motion_video": False,       # aplica o movimento também em clipes de vídeo
    "transition": "cut",         # ver TRANSITIONS
    "transition_dur": 0.35,
    "effects": {"chroma": 0.0, "glitch": 0.0, "scanlines": 0.0, "shake": 0.0,
                "flicker": 0.0, "sharpen": 0.0, "soft": 0.0, "pixel": 0.0, "mirror": False},
    "overlays": {"verse_cards": False, "callouts": False, "topic_bar": False},
    "cta": {"enabled": False, "position": "end", "anchor": "top", "language": "auto",
            "style": "red", "seconds": 5.0, "text": ""},
    "subtitles": {
        "enabled": True, "mode": "block", "font": "Poppins", "bold": True, "size": 0.045,
        "color": "#FFFFFF", "outline_color": "#000000", "outline": 0.09, "shadow": 0.03,
        "box": False, "box_opacity": 0.55, "position": "bottom", "uppercase": False,
        "highlight": "#FFD60A", "words": 3, "animation": "fade",
    },
}

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "documentario", "name": "Documentário cinematográfico",
        "tagline": "Cores levemente teal e laranja, faixas de cinema, zoom lento e legenda em serifa.",
        "tags": ["16:9", "calmo", "história"], "pacing": "slow", "ratio": "16:9",
        "audio": {"music_volume": 0.14, "ducking": True},
        "style": {
            "grade": {"contrast": 1.08, "saturation": 0.92, "balance": {"rs": -0.04, "bs": 0.05, "rh": 0.06, "bh": -0.05}},
            "vignette": 0.35, "grain": 5, "letterbox": False, "motion": "alternate", "motion_strength": 0.10,
            "transition": "fade", "transition_dur": 0.45,
            "subtitles": {"font": "DM Serif Display", "bold": False, "size": 0.052, "outline": 0.06, "shadow": 0.05, "animation": "fade"},
        },
    },
    {
        "id": "historia_sepia", "name": "História em sépia",
        "tagline": "Tom de fotografia antiga com vinheta e grão. Ideal para história de empresas e pessoas.",
        "tags": ["16:9", "história", "retrô"], "pacing": "slow", "ratio": "16:9",
        "audio": {"music_volume": 0.13, "ducking": True},
        "style": {
            "grade": {"sepia": True, "contrast": 1.06, "saturation": 1.0, "brightness": -0.01},
            "vignette": 0.55, "grain": 12, "motion": "zoom_in", "motion_strength": 0.12,
            "transition": "fade", "transition_dur": 0.5,
            "subtitles": {"font": "DM Serif Display", "bold": False, "size": 0.05, "color": "#F6EAD0", "outline_color": "#2B1A0B", "outline": 0.07, "animation": "fade"},
        },
    },
    {
        "id": "noir", "name": "Noir preto e branco",
        "tagline": "Monocromático de alto contraste, grão pesado e legenda condensada.",
        "tags": ["16:9", "dramático"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.15, "ducking": True},
        "style": {
            "grade": {"mono": True, "contrast": 1.22, "brightness": -0.02},
            "vignette": 0.5, "grain": 14, "letterbox": False, "motion": "drift", "motion_strength": 0.10,
            "transition": "fade", "transition_dur": 0.4,
            "subtitles": {"font": "Bebas Neue", "bold": False, "size": 0.062, "uppercase": True, "outline": 0.06, "animation": "fade"},
        },
    },
    {
        "id": "misterio", "name": "Mistério sombrio",
        "tagline": "Cores dessaturadas e frias, vinheta forte e destaque vermelho palavra a palavra.",
        "tags": ["16:9", "true crime", "palavra a palavra"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.16, "ducking": True},
        "style": {
            "grade": {"saturation": 0.55, "contrast": 1.16, "brightness": -0.04, "balance": {"rs": -0.05, "bs": 0.07, "bm": 0.03}},
            "vignette": 0.65, "grain": 8, "motion": "zoom_in", "motion_strength": 0.11,
            "transition": "fade", "transition_dur": 0.4,
            "subtitles": {"mode": "word", "font": "Poppins", "bold": True, "size": 0.05, "words": 3, "highlight": "#FF4D5E", "position": "lower_third", "animation": "none"},
        },
    },
    {
        "id": "economia", "name": "Economia e finanças",
        "tagline": "Visual frio e limpo, deslize suave e destaque dourado nas palavras.",
        "tags": ["16:9", "dados", "palavra a palavra"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.12, "ducking": True},
        "style": {
            "grade": {"saturation": 0.86, "contrast": 1.1, "balance": {"bs": 0.05, "bh": 0.03, "rh": -0.02}},
            "vignette": 0.25, "grain": 3, "motion": "drift", "motion_strength": 0.10,
            "transition": "fade", "transition_dur": 0.3,
            "subtitles": {"mode": "word", "font": "Poppins", "bold": True, "size": 0.048, "words": 3, "highlight": "#F5B83D", "animation": "none"},
        },
    },
    {
        "id": "viral", "name": "Legenda viral",
        "tagline": "Letras grandes no centro, palavra ativa em amarelo e zoom de impacto. Estilo de retenção.",
        "tags": ["9:16", "16:9", "palavra a palavra"], "pacing": "fast", "ratio": "9:16",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "grade": {"saturation": 1.15, "contrast": 1.08},
            "motion": "zoom_in", "motion_strength": 0.12, "motion_video": True, "transition": "cut",
            "subtitles": {"mode": "word", "font": "Anton", "bold": False, "size": 0.075, "uppercase": True, "words": 3, "outline": 0.1, "shadow": 0.06, "highlight": "#FFD60A", "position": "middle", "animation": "pop"},
        },
    },
    {
        "id": "remotion_doc", "name": "Documentário escuro (Remotion)",
        "tagline": "Ken Burns alternando zoom, vinheta pesada e uma palavra por vez em caixa escura.",
        "tags": ["16:9", "palavra a palavra", "dark"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.12, "ducking": True},
        "style": {
            "grade": {"contrast": 1.1, "saturation": 0.9, "brightness": -0.12},
            "vignette": 0.85, "grain": 0, "motion": "alternate", "motion_strength": 0.15, "motion_video": True,
            "transition": "cut",
            "subtitles": {"mode": "word", "font": "Poppins", "bold": True, "size": 0.046, "words": 1, "uppercase": True, "color": "#F1F1F1", "highlight": "#F1F1F1",
                          "box": True, "box_opacity": 0.4, "outline": 0.0, "shadow": 0.0, "animation": "none", "position": "bottom"},
        },
    },
    {
        "id": "biblico", "name": "Documentário bíblico",
        "tagline": "Tom de deserto e pergaminho, zoom lento e cartões de versículo dourados quando o texto cita uma passagem.",
        "tags": ["16:9", "bíblico", "cartões"], "pacing": "slow", "ratio": "16:9",
        "audio": {"music_volume": 0.12, "ducking": True},
        "style": {
            "grade": {"sepia": 0.15, "contrast": 1.15, "brightness": -0.12, "saturation": 0.95},
            "vignette": 0.85, "grain": 4, "motion": "alternate", "motion_strength": 0.12, "motion_video": True,
            "transition": "fade", "transition_dur": 0.6,
            "overlays": {"verse_cards": True},
            "subtitles": {"font": "EB Garamond", "bold": False, "size": 0.056, "color": "#FEF3C7", "outline_color": "#0F0A05", "outline": 0.07, "shadow": 0.05, "position": "lower_third", "animation": "fade"},
        },
    },
    {
        "id": "papel_callout", "name": "Etiqueta de papel e apontamento",
        "tagline": "Etiquetas brancas com borda preta apontam para a imagem por uma linha tracejada. Barra de tópico no canto.",
        "tags": ["16:9", "explicativo", "callout"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "grade": {}, "motion": "none", "transition": "cut",
            "overlays": {"callouts": True, "topic_bar": True},
            "subtitles": {"enabled": False, "font": "Poppins", "bold": True, "size": 0.042, "box": True, "box_opacity": 0.6, "outline": 0.0, "shadow": 0.0, "animation": "none"},
        },
    },
    {
        "id": "shorts", "name": "Shorts impactante",
        "tagline": "Cortes rápidos, flash branco entre cenas e duas palavras por vez.",
        "tags": ["9:16", "rápido", "palavra a palavra"], "pacing": "fast", "ratio": "9:16",
        "audio": {"music_volume": 0.12, "ducking": True},
        "style": {
            "grade": {"saturation": 1.2, "contrast": 1.1},
            "motion": "alternate", "motion_strength": 0.14, "motion_video": True,
            "transition": "flash", "transition_dur": 0.14,
            "subtitles": {"mode": "word", "font": "Archivo Black", "bold": False, "size": 0.06, "uppercase": True, "words": 2, "outline": 0.1, "highlight": "#4CF2C8", "position": "lower_third", "animation": "pop"},
        },
    },
    {
        "id": "noticia", "name": "Notícia e explicativo",
        "tagline": "Imagem limpa, cortes secos e legenda em caixa escura, fácil de ler.",
        "tags": ["16:9", "limpo"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "grade": {"contrast": 1.05, "saturation": 1.05},
            "motion": "none", "transition": "cut",
            "subtitles": {"font": "Poppins", "bold": True, "size": 0.042, "box": True, "box_opacity": 0.6, "outline": 0.0, "shadow": 0.0, "animation": "none"},
        },
    },
    {
        "id": "neon", "name": "Tecnologia neon",
        "tagline": "Cores saturadas com tom ciano e magenta, zoom e flash curto entre cenas.",
        "tags": ["16:9", "tecnologia"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.14, "ducking": True},
        "style": {
            "grade": {"saturation": 1.25, "contrast": 1.12, "balance": {"bs": 0.07, "rs": -0.06, "rh": 0.05, "bm": 0.04}},
            "vignette": 0.3, "motion": "zoom_in", "motion_strength": 0.10, "transition": "flash", "transition_dur": 0.16,
            "subtitles": {"mode": "word", "font": "Archivo Black", "bold": False, "size": 0.048, "words": 3, "highlight": "#35E0FF", "outline": 0.09, "animation": "none"},
        },
    },
    {
        "id": "vhs", "name": "VHS retrô",
        "tagline": "Curva vintage, grão forte e cores quentes. Legenda amarela estilo fita.",
        "tags": ["16:9", "retrô"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.15, "ducking": True},
        "style": {
            "grade": {"curve": "vintage", "saturation": 1.3, "contrast": 1.05},
            "vignette": 0.3, "grain": 22, "motion": "drift", "motion_strength": 0.08, "transition": "flash", "transition_dur": 0.12,
            "subtitles": {"font": "Bebas Neue", "bold": False, "size": 0.066, "color": "#FFE94A", "outline": 0.08, "uppercase": True, "animation": "none"},
        },
    },
    {
        "id": "minimalista", "name": "Minimalista",
        "tagline": "Sem filtro de cor, cortes secos e legenda discreta. Deixa a mídia falar.",
        "tags": ["16:9", "limpo"], "pacing": "balanced", "ratio": "16:9",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "motion": "none", "transition": "cut",
            "subtitles": {"font": "Poppins", "bold": True, "size": 0.038, "outline": 0.08, "shadow": 0.04, "animation": "fade"},
        },
    },
    # ---------------------------------------------------------- novos templates (pesquisa GitHub + xfade)
    {
        "id": "true_crime", "name": "True crime moderno",
        "tagline": "Frio, contrastado e com câmera na mão. Palavra a palavra vermelha e flash para preto entre cenas.",
        "tags": ["16:9", "true crime", "dark"], "pacing": "balanced", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.15, "ducking": True},
        "style": {
            "grade": {"saturation": 0.62, "contrast": 1.22, "brightness": -0.07, "balance": {"rs": -0.06, "bs": 0.08, "bm": 0.04}},
            "vignette": 0.72, "grain": 10, "letterbox": False, "motion": "handheld", "motion_strength": 0.10, "motion_video": True,
            "transition": "fadeblack", "transition_dur": 0.45,
            "effects": {"chroma": 0.12, "scanlines": 0.06},
            "cta": {"enabled": True, "position": "end", "anchor": "top", "style": "dark", "seconds": 5.0},
            "subtitles": {"mode": "word", "font": "Poppins", "bold": True, "size": 0.05, "words": 3, "highlight": "#FF3B4F", "position": "lower_third", "animation": "none"},
        },
    },
    {
        "id": "cyberpunk", "name": "Cyberpunk neon",
        "tagline": "Ciano e magenta, aberração cromática, glitch e punch-in. Transição em pixel dissolve.",
        "tags": ["16:9", "9:16", "tecnologia", "neon"], "pacing": "fast", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.13, "ducking": True},
        "style": {
            "grade": {"saturation": 1.35, "contrast": 1.16, "balance": {"bs": 0.09, "rs": -0.07, "rh": 0.05, "bm": 0.05}},
            "vignette": 0.42, "grain": 4, "motion": "punch_in", "motion_strength": 0.14, "motion_video": True,
            "transition": "pixelize", "transition_dur": 0.32,
            "effects": {"chroma": 0.35, "glitch": 0.22, "scanlines": 0.10},
            "cta": {"enabled": True, "position": "middle", "anchor": "bottom", "style": "neon", "seconds": 4.5},
            "subtitles": {"mode": "word", "font": "Archivo Black", "bold": False, "size": 0.048, "words": 3, "highlight": "#35E0FF", "outline": 0.1, "animation": "pop"},
        },
    },
    {
        "id": "vhs_glitch", "name": "VHS glitch",
        "tagline": "Fita velha com linhas de varredura, tremor e cores quentes. Transição de desfoque horizontal.",
        "tags": ["16:9", "retrô", "glitch"], "pacing": "balanced", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.14, "ducking": True},
        "style": {
            "grade": {"curve": "vintage", "saturation": 1.28, "contrast": 1.08, "brightness": 0.01},
            "vignette": 0.38, "grain": 24, "motion": "handheld", "motion_strength": 0.08, "motion_video": True,
            "transition": "hblur", "transition_dur": 0.28,
            "effects": {"scanlines": 0.35, "glitch": 0.18, "chroma": 0.16, "flicker": 0.14},
            "subtitles": {"font": "Bebas Neue", "bold": False, "size": 0.066, "color": "#FFE94A", "outline": 0.08, "uppercase": True, "animation": "none"},
        },
    },
    {
        "id": "luma_cinema", "name": "Luma cinema",
        "tagline": "Cinema limpo com faixas largas, zoom lento, nitidez e flash branco suave na troca de cena.",
        "tags": ["16:9", "cinema", "premium"], "pacing": "slow", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.11, "ducking": True},
        "style": {
            "grade": {"contrast": 1.14, "saturation": 0.94, "brightness": -0.03},
            "vignette": 0.40, "grain": 4, "letterbox": False, "motion": "zoom_in", "motion_strength": 0.09,
            "transition": "fadewhite", "transition_dur": 0.55,
            "effects": {"sharpen": 0.35, "soft": 0.08},
            "cta": {"enabled": True, "position": "end", "anchor": "top", "style": "minimal", "seconds": 5.0},
            "subtitles": {"font": "DM Serif Display", "bold": False, "size": 0.05, "outline": 0.06, "shadow": 0.05, "animation": "fade"},
        },
    },
    {
        "id": "iris_doc", "name": "Íris documental",
        "tagline": "Documentário com transição de íris circular, câmera alternando zoom e legenda sóbria.",
        "tags": ["16:9", "documentário", "íris"], "pacing": "slow", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.11, "ducking": True},
        "style": {
            "grade": {"contrast": 1.10, "saturation": 0.88, "balance": {"rs": -0.03, "bs": 0.05}},
            "vignette": 0.50, "grain": 6, "motion": "alternate", "motion_strength": 0.11,
            "transition": "circleopen", "transition_dur": 0.70,
            "subtitles": {"font": "EB Garamond", "bold": False, "size": 0.052, "outline": 0.06, "shadow": 0.04, "animation": "fade"},
        },
    },
    {
        "id": "editorial_push", "name": "Editorial push",
        "tagline": "Revista em movimento: panorâmica lateral, empurrão entre cenas e imagem nítida.",
        "tags": ["16:9", "editorial", "limpo"], "pacing": "balanced", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "grade": {"contrast": 1.08, "saturation": 1.02},
            "vignette": 0.18, "grain": 2, "motion": "pan_right", "motion_strength": 0.10, "motion_video": True,
            "transition": "slideleft", "transition_dur": 0.38,
            "effects": {"sharpen": 0.45},
            "subtitles": {"font": "Poppins", "bold": True, "size": 0.042, "outline": 0.08, "shadow": 0.03, "animation": "fade"},
        },
    },
    {
        "id": "blinds_history", "name": "Persianas da história",
        "tagline": "Sépia antiga com transição de persianas horizontais e panorâmica vertical lenta.",
        "tags": ["16:9", "história", "retrô"], "pacing": "slow", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.12, "ducking": True},
        "style": {
            "grade": {"sepia": 0.55, "contrast": 1.12, "saturation": 0.92, "brightness": -0.04},
            "vignette": 0.62, "grain": 15, "motion": "pan_up", "motion_strength": 0.10,
            "transition": "hlslice", "transition_dur": 0.65,
            "effects": {"soft": 0.18, "flicker": 0.10},
            "subtitles": {"font": "Cinzel", "bold": True, "size": 0.048, "color": "#F6EAD0", "outline_color": "#2B1A0B", "outline": 0.07, "animation": "fade"},
        },
    },
    {
        "id": "short_hype", "name": "Short hype",
        "tagline": "Shorts vertical com punch-in, flash branco e chamada de inscrição no começo.",
        "tags": ["9:16", "rápido", "shorts"], "pacing": "fast", "ratio": "9:16", "source": "github",
        "audio": {"music_volume": 0.12, "ducking": True},
        "style": {
            "grade": {"saturation": 1.30, "contrast": 1.14},
            "motion": "punch_in", "motion_strength": 0.18, "motion_video": True,
            "transition": "fadewhite", "transition_dur": 0.18,
            "effects": {"sharpen": 0.30},
            "cta": {"enabled": True, "position": "start", "anchor": "top", "style": "red", "seconds": 3.5},
            "subtitles": {"mode": "word", "font": "Anton", "bold": False, "size": 0.072, "uppercase": True, "words": 2, "outline": 0.1, "shadow": 0.05, "highlight": "#FFD60A", "position": "middle", "animation": "pop"},
        },
    },
    {
        "id": "news_alert", "name": "Alerta de notícia",
        "tagline": "Corte seco, barra de tópico e chamada vermelha de inscrição no fim. Leitura rápida.",
        "tags": ["16:9", "notícia", "urgente"], "pacing": "balanced", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "grade": {"contrast": 1.10, "saturation": 1.06},
            "motion": "none", "transition": "cut",
            "overlays": {"topic_bar": True, "callouts": True},
            "cta": {"enabled": True, "position": "end", "anchor": "top", "style": "red", "seconds": 5.0},
            "subtitles": {"font": "Poppins", "bold": True, "size": 0.044, "box": True, "box_opacity": 0.62, "outline": 0.0, "shadow": 0.0, "animation": "none"},
        },
    },
    {
        "id": "luxury_minimal", "name": "Luxury minimal",
        "tagline": "Preto e dourado, dissolve elegante, serifa fina e assinatura discreta no fim.",
        "tags": ["16:9", "premium", "minimal"], "pacing": "slow", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.09, "ducking": True},
        "style": {
            "grade": {"contrast": 1.12, "saturation": 0.82, "brightness": -0.06},
            "vignette": 0.55, "grain": 3, "letterbox": False, "motion": "pan_down", "motion_strength": 0.07,
            "transition": "crossfade", "transition_dur": 0.80,
            "effects": {"soft": 0.10},
            "cta": {"enabled": True, "position": "end", "anchor": "top", "style": "gold", "seconds": 5.0},
            "subtitles": {"font": "Cinzel", "bold": True, "size": 0.042, "color": "#F5E6C8", "outline_color": "#1A1206", "outline": 0.06, "animation": "fade"},
        },
    },
    {
        "id": "tech_explainer", "name": "Tech explainer",
        "tagline": "Explicativo tech com etiquetas, dissolve, órbita suave e inscrição neon no meio.",
        "tags": ["16:9", "tecnologia", "explicativo"], "pacing": "balanced", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.10, "ducking": True},
        "style": {
            "grade": {"saturation": 1.16, "contrast": 1.08, "balance": {"bs": 0.06, "rh": -0.03}},
            "vignette": 0.22, "grain": 2, "motion": "orbit", "motion_strength": 0.08,
            "transition": "dissolve", "transition_dur": 0.42,
            "effects": {"sharpen": 0.35, "chroma": 0.06},
            "overlays": {"callouts": True, "topic_bar": True},
            "cta": {"enabled": True, "position": "middle", "anchor": "bottom", "style": "neon", "seconds": 4.5},
            "subtitles": {"mode": "word", "font": "Poppins", "bold": True, "size": 0.046, "words": 3, "highlight": "#35E0FF", "position": "lower_third", "animation": "none"},
        },
    },
    {
        "id": "dark_archive", "name": "Arquivo sombrio",
        "tagline": "Material de arquivo: cortina de cinza, grão pesado, tremor e legenda tipo máquina.",
        "tags": ["16:9", "dark", "arquivo"], "pacing": "slow", "ratio": "16:9", "source": "github",
        "audio": {"music_volume": 0.13, "ducking": True},
        "style": {
            "grade": {"sepia": 0.22, "mono": False, "contrast": 1.20, "saturation": 0.70, "brightness": -0.08},
            "vignette": 0.78, "grain": 18, "letterbox": False, "motion": "handheld", "motion_strength": 0.09, "motion_video": True,
            "transition": "fadegrays", "transition_dur": 0.60,
            "effects": {"scanlines": 0.12, "flicker": 0.12, "chroma": 0.08},
            "cta": {"enabled": True, "position": "end", "anchor": "top", "style": "dark", "seconds": 5.0},
            "subtitles": {"font": "Bebas Neue", "bold": False, "size": 0.056, "color": "#E8E8E8", "outline": 0.07, "uppercase": True, "animation": "none"},
        },
    },
]
TEMPLATE_INDEX = {t["id"]: t for t in TEMPLATES}
DEFAULT_TEMPLATE = "documentario"

PACING = {
    "fast": {"label": "Rápido", "span": 7.0, "words": 16},
    "balanced": {"label": "Médio", "span": 13.0, "words": 30},
    "slow": {"label": "Lento", "span": 25.0, "words": 38},
}


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def sanitize_overrides(raw: Any) -> dict[str, Any]:
    """Aceita só os ajustes que a interface oferece, com limites seguros."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    if raw.get("motion") in MOTIONS:
        out["motion"] = raw["motion"]
    if raw.get("transition") in TRANSITIONS:
        out["transition"] = raw["transition"]
    for key in ("letterbox", "motion_video"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    if isinstance(raw.get("vignette"), (int, float)):
        out["vignette"] = max(0.0, min(1.0, float(raw["vignette"])))
    if isinstance(raw.get("grain"), (int, float)):
        out["grain"] = int(max(0, min(30, raw["grain"])))
    if isinstance(raw.get("motion_strength"), (int, float)):
        out["motion_strength"] = max(0.02, min(0.3, float(raw["motion_strength"])))
    if isinstance(raw.get("transition_dur"), (int, float)):
        out["transition_dur"] = max(0.05, min(1.5, float(raw["transition_dur"])))
    ov = raw.get("overlays")
    if isinstance(ov, dict):
        o = {k: ov[k] for k in ("verse_cards", "callouts", "topic_bar") if isinstance(ov.get(k), bool)}
        if o:
            out["overlays"] = o
    fx = raw.get("effects")
    if isinstance(fx, dict):
        e: dict[str, Any] = {}
        for key in EFFECTS:
            if key == "mirror":
                if isinstance(fx.get(key), bool):
                    e[key] = fx[key]
            elif isinstance(fx.get(key), (int, float)):
                e[key] = max(0.0, min(1.0, float(fx[key])))
        if e:
            out["effects"] = e
    cta = raw.get("cta")
    if isinstance(cta, dict):
        c: dict[str, Any] = {}
        if isinstance(cta.get("enabled"), bool):
            c["enabled"] = cta["enabled"]
        if cta.get("position") in ("start", "middle", "end"):
            c["position"] = cta["position"]
        if cta.get("anchor") in ("top", "bottom"):
            c["anchor"] = cta["anchor"]
        if cta.get("language") in ("auto", "pt", "en", "es"):
            c["language"] = cta["language"]
        if cta.get("style") in CTA_STYLES:
            c["style"] = cta["style"]
        if isinstance(cta.get("seconds"), (int, float)):
            c["seconds"] = max(1.5, min(12.0, float(cta["seconds"])))
        if isinstance(cta.get("text"), str):
            c["text"] = " ".join(cta["text"].split())[:80]
        if c:
            out["cta"] = c
    grade = raw.get("grade")
    if isinstance(grade, dict):
        g: dict[str, Any] = {}
        for key in ("mono", "sepia"):
            if isinstance(grade.get(key), bool):
                g[key] = grade[key]
            elif key == "sepia" and isinstance(grade.get(key), (int, float)):
                g[key] = max(0.0, min(1.0, float(grade[key])))
        for key, lo, hi in (("contrast", 0.5, 1.8), ("saturation", 0.0, 2.0), ("brightness", -0.3, 0.3)):
            if isinstance(grade.get(key), (int, float)):
                g[key] = max(lo, min(hi, float(grade[key])))
        if g:
            out["grade"] = g
    subs = raw.get("subtitles")
    if isinstance(subs, dict):
        s: dict[str, Any] = {}
        if isinstance(subs.get("enabled"), bool):
            s["enabled"] = subs["enabled"]
        if subs.get("mode") in ("block", "word"):
            s["mode"] = subs["mode"]
        if subs.get("position") in ("bottom", "lower_third", "middle", "top"):
            s["position"] = subs["position"]
        if subs.get("animation") in ("none", "fade", "pop"):
            s["animation"] = subs["animation"]
        for key in ("uppercase", "box"):
            if isinstance(subs.get(key), bool):
                s[key] = subs[key]
        if subs.get("font") in FONT_FAMILIES:
            s["font"] = subs["font"]
            s["bold"] = FONT_FAMILIES[subs["font"]]["bold"]
        for key in ("color", "highlight", "outline_color"):
            if isinstance(subs.get(key), str) and _HEX.match(subs[key]):
                s[key] = subs[key].upper()
        if isinstance(subs.get("size"), (int, float)):
            s["size"] = max(0.025, min(0.11, float(subs["size"])))
        if isinstance(subs.get("words"), (int, float)):
            s["words"] = int(max(1, min(5, subs["words"])))
        if s:
            out["subtitles"] = s
    for key in ("cor_primaria", "paleta"):
        if isinstance(raw.get(key), str) and _HEX.match(raw[key]):
            out[key] = raw[key].upper()
    return out


def resolve_style(template_id: str | None, overrides: Any = None) -> dict[str, Any]:
    template = TEMPLATE_INDEX.get(template_id or "") or TEMPLATE_INDEX[DEFAULT_TEMPLATE]
    style = deep_merge(BASE_STYLE, template.get("style", {}))
    return deep_merge(style, sanitize_overrides(overrides))


def public_templates() -> list[dict[str, Any]]:
    out = []
    for t in TEMPLATES:
        out.append({
            "id": t["id"], "name": t["name"], "tagline": t["tagline"], "tags": t["tags"],
            "pacing": t["pacing"], "ratio": t["ratio"], "audio": t["audio"],
            "source": t.get("source", "projeto"),
            "style": resolve_style(t["id"]),
        })
    return out


# ------------------------------------------------------------------ dimensões e filtros

def ratio_dimensions(ratio: str, quality: str) -> tuple[int, int]:
    """A qualidade vale para o lado menor: 720p = 1280x720, 720x1280 ou 720x720."""
    short = 1080 if quality == "1080p" else 720
    if ratio == "9:16":
        return short, int(short * 16 / 9) // 2 * 2
    if ratio == "1:1":
        return short, short
    return int(short * 16 / 9) // 2 * 2, short


def _fq(path: Path | str) -> str:
    """Escapa um caminho para uso dentro de um filtro do FFmpeg."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def grade_filters(g: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    if g.get("curve"):
        parts.append(f"curves=preset={g['curve']}")
    if g.get("sepia"):
        a = 1.0 if g["sepia"] is True else float(g["sepia"])
        m = [(.393, .769, .189), (.349, .686, .168), (.272, .534, .131)]
        ident = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        v = [round(ident[i][j] * (1 - a) + m[i][j] * a, 4) for i in range(3) for j in range(3)]
        parts.append("colorchannelmixer=" + ":".join(str(x) for x in [v[0], v[1], v[2], 0, v[3], v[4], v[5], 0, v[6], v[7], v[8], 0]))
    if g.get("mono"):
        parts.append("hue=s=0")
    bal = g.get("balance")
    if bal:
        parts.append("colorbalance=" + ":".join(f"{k}={v}" for k, v in bal.items()))
    c, s, b, gm = g.get("contrast", 1.0), g.get("saturation", 1.0), g.get("brightness", 0.0), g.get("gamma", 1.0)
    if (c, s, b, gm) != (1.0, 1.0, 0.0, 1.0):
        parts.append(f"eq=contrast={c:.3f}:saturation={s:.3f}:brightness={b:.3f}:gamma={gm:.3f}")
    return parts


def _motion_zoompan(motion: str, strength: float, frames: int, index: int, w: int, h: int) -> tuple[str, str, str]:
    """Devolve (zoom, x, y) para o filtro zoompan das fotos."""
    s = max(0.01, float(strength))
    f = max(1, frames)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "zoom_in":
        return f"1+{s:.4f}*on/{f}", cx, cy
    if motion == "zoom_out":
        return f"{1 + s:.4f}-{s:.4f}*on/{f}", cx, cy
    if motion == "drift":
        x = f"(iw-iw/zoom)*on/{f}" if index % 2 == 0 else f"(iw-iw/zoom)*(1-on/{f})"
        return f"{1 + s:.4f}", x, cy
    if motion == "pan_left":
        return f"{1 + s:.4f}", f"(iw-iw/zoom)*(1-on/{f})", cy
    if motion == "pan_right":
        return f"{1 + s:.4f}", f"(iw-iw/zoom)*on/{f}", cy
    if motion == "pan_up":
        return f"{1 + s:.4f}", cx, f"(ih-ih/zoom)*(1-on/{f})"
    if motion == "pan_down":
        return f"{1 + s:.4f}", cx, f"(ih-ih/zoom)*on/{f}"
    if motion == "diagonal_in":
        return f"1+{s:.4f}*on/{f}", f"(iw-iw/zoom)*(1-on/{f})", f"(ih-ih/zoom)*(1-on/{f})"
    if motion == "diagonal_out":
        return f"{1 + s:.4f}-{s:.4f}*on/{f}", f"(iw-iw/zoom)*on/{f}", f"(ih-ih/zoom)*on/{f}"
    if motion == "punch_in":
        return f"1+{s * 2:.4f}*(on/{f})*(on/{f})", cx, cy
    if motion == "handheld":
        amp = max(2, int(h * 0.03))
        return (f"{1 + s:.4f}", f"iw/2-(iw/zoom/2)+sin(on/2.7)*{amp}",
                f"ih/2-(ih/zoom/2)+cos(on/3.3)*{amp}")
    if motion == "orbit":
        amp = max(2, int(min(w, h) * 0.035))
        return (f"{1 + s:.4f}", f"iw/2-(iw/zoom/2)+cos(2*PI*on/{f})*{amp}",
                f"ih/2-(ih/zoom/2)+sin(2*PI*on/{f})*{amp}")
    return "1", cx, cy


def _video_motion_filters(motion: str, strength: float, dur: float, w: int, h: int, index: int) -> list[str]:
    """Movimento de câmera para clipes de vídeo (crop animado ou zoom dinâmico)."""
    s = max(0.01, float(strength))
    d = max(0.1, float(dur))
    if motion in ("zoom_in", "zoom_out"):
        grow = f"{s:.4f}*t/{d:.3f}" if motion == "zoom_in" else f"{s:.4f}*(1-t/{d:.3f})"
        return [f"scale=w='trunc({w}*(1+{grow})/2)*2':h=-2:eval=frame,crop={w}:{h}"]
    if motion == "alternate":
        motion = "zoom_in" if index % 2 == 0 else "zoom_out"
        return _video_motion_filters(motion, s, dur, w, h, index)
    if motion == "none":
        return []
    factor = 1 + s
    sw = int(round(w * factor / 2) * 2)
    out: list[str] = [f"scale={sw}:-2"]
    cx, cy = "(iw-ow)/2", "(ih-oh)/2"
    amp = max(2, int(h * 0.012))
    if motion == "pan_left":
        x, y = f"(iw-ow)*(1-t/{d:.3f})", cy
    elif motion == "pan_right":
        x, y = f"(iw-ow)*(t/{d:.3f})", cy
    elif motion == "pan_up":
        x, y = cx, f"(ih-oh)*(1-t/{d:.3f})"
    elif motion == "pan_down":
        x, y = cx, f"(ih-oh)*(t/{d:.3f})"
    elif motion == "diagonal_in":
        x, y = f"(iw-ow)*(1-t/{d:.3f})", f"(ih-oh)*(1-t/{d:.3f})"
    elif motion == "diagonal_out":
        x, y = f"(iw-ow)*(t/{d:.3f})", f"(ih-oh)*(t/{d:.3f})"
    elif motion == "handheld":
        x = f"max(0,min(iw-ow,(iw-ow)/2+sin(t*2.2)*{amp}))"
        y = f"max(0,min(ih-oh,(ih-oh)/2+cos(t*1.8)*{amp}))"
    elif motion == "orbit":
        rx, ry = max(2, int(w * 0.02)), max(2, int(h * 0.02))
        x = f"max(0,min(iw-ow,(iw-ow)/2+cos(2*PI*t/{d:.3f})*{rx}))"
        y = f"max(0,min(ih-oh,(ih-oh)/2+sin(2*PI*t/{d:.3f})*{ry}))"
    elif motion == "drift":
        x = f"(iw-ow)*(t/{d:.3f})" if index % 2 == 0 else f"(iw-ow)*(1-t/{d:.3f})"
        y = cy
    else:  # punch_in e fallback
        x, y = cx, cy
    out.append(f"crop={w}:{h}:{x}:{y}")
    return out


def effects_filters(style: dict[str, Any], w: int, h: int) -> list[str]:
    """Efeitos visuais opcionais, todos com intensidade 0–1."""
    fx = style.get("effects") or {}
    parts: list[str] = []
    if fx.get("mirror"):
        parts.append("hflip")
    pixel = float(fx.get("pixel") or 0)
    if pixel > 0:
        block = max(2, int(18 - 13 * pixel))
        parts.append(f"scale=trunc(iw/{block})*{block}:-2:flags=neighbor,scale={w}:{h}:flags=neighbor")
    chroma = float(fx.get("chroma") or 0)
    if chroma > 0:
        px = max(1, int(round(1 + chroma * 7)))
        parts.append(f"rgbashift=rh={px}:bh=-{px}")
    glitch = float(fx.get("glitch") or 0)
    if glitch > 0:
        px = max(1, int(round(1 + glitch * 6)))
        parts.append(f"chromashift=cbh={px}:crh=-{px}")
        parts.append(f"noise=alls={max(2, int(4 + glitch * 12))}:allf=t")
    scan = float(fx.get("scanlines") or 0)
    if scan > 0:
        cell = max(2, int(h / 180))
        parts.append(f"drawgrid=w=iw:h={cell}:t=1:c=black@{round(0.08 + scan * 0.30, 2)}")
    shake = float(fx.get("shake") or 0)
    if shake > 0:
        amp = max(1, int(round(1 + shake * 6)))
        parts.append(f"crop=iw-{amp * 2}:ih-{amp * 2}:{amp}+{amp}*sin(t*17):{amp}+{amp}*cos(t*13),scale={w}:{h}")
    flicker = float(fx.get("flicker") or 0)
    if flicker > 0:
        parts.append(f"eq=brightness={round(0.012 + flicker * 0.035, 3)}:contrast={round(1 + flicker * 0.05, 3)}")
        parts.append(f"noise=alls={max(1, int(1 + flicker * 5))}:allf=t")
    sharpen = float(fx.get("sharpen") or 0)
    if sharpen > 0:
        parts.append(f"unsharp=5:5:{round(0.35 + sharpen * 1.25, 2)}:5:5:0")
    soft = float(fx.get("soft") or 0)
    if soft > 0:
        parts.append(f"gblur=sigma={round(0.35 + soft * 1.8, 2)}")
    return parts


def segment_filter(style: dict[str, Any], w: int, h: int, fps: int, frames: int, index: int, *,
                   is_image: bool, first: bool, last: bool, ratio: str) -> tuple[str, bool]:
    """Monta o filtro de um clipe. Retorna (filtro, imagem_precisa_de_loop)."""
    motion = style.get("motion", "none")
    if motion == "alternate":
        motion = "zoom_in" if index % 2 == 0 else "zoom_out"
    strength = float(style.get("motion_strength", 0.1))
    dur = max(0.1, frames / fps)
    chain: list[str] = []
    needs_loop = True
    if is_image and motion in MOTIONS and motion != "none":
        needs_loop = False
        chain.append(f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2}")
        z, x, y = _motion_zoompan(motion, strength, frames, index, w, h)
        chain.append(f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps}")
    else:
        chain.append(f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
        if not is_image and style.get("motion_video"):
            chain += _video_motion_filters(motion, strength, dur, w, h, index)
        chain.append(f"fps={fps}")
    chain.append("setsar=1")
    chain += grade_filters(style.get("grade", {}))
    chain += effects_filters(style, w, h)
    vig = float(style.get("vignette", 0))
    if vig > 0:
        chain.append(f"vignette=angle={round(1.3 - 0.8 * vig, 3)}")
    grain = int(style.get("grain", 0))
    if grain > 0:
        chain.append(f"noise=alls={grain}:allf=t")
    if style.get("letterbox") and ratio == "16:9":
        bar = int((h - w / 2.39) / 2) // 2 * 2
        if bar > 0:
            chain.append(f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill,drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill")
    tr = style.get("transition", "cut")
    if tr in ("fade", "flash"):
        td = min(float(style.get("transition_dur", 0.35)), dur / 3)
        color = "white" if tr == "flash" else "black"
        if not first:
            chain.append(f"fade=t=in:st=0:d={td:.3f}:c={color}")
        if not last:
            chain.append(f"fade=t=out:st={max(0.0, dur - td):.3f}:d={td:.3f}:c={color}")
    chain.append("format=yuv420p")
    return ",".join(chain), needs_loop


# ------------------------------------------------------------------ legendas (ASS)

def _ass_color(hex_color: str, alpha: float = 1.0) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    a = int(round((1 - alpha) * 255))
    return f"&H{a:02X}{b}{g}{r}".upper()


def _ass_time(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    hh, rem = divmod(cs, 360000)
    mm, rem = divmod(rem, 6000)
    ss, cs = divmod(rem, 100)
    return f"{hh}:{mm:02d}:{ss:02d}.{cs:02d}"


def _ass_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(cues: list[dict[str, Any]], style: dict[str, Any], w: int, h: int, ratio: str,
              scenes: list[dict[str, Any]] | None = None, preview: bool = False) -> str:
    sub = style["subtitles"]
    portrait = h > w
    size_px = max(14, int(sub["size"] * h * (0.8 if portrait else 1.0)))
    outline_px = round(size_px * float(sub.get("outline", 0.08)), 1)
    shadow_px = round(size_px * float(sub.get("shadow", 0.03)), 1)
    pos = sub.get("position", "bottom")
    bar = int((h - w / 2.39) / 2) if (style.get("letterbox") and ratio == "16:9") else 0
    alignment, margin_v = {
        "bottom": (2, int(h * 0.07) + bar), "lower_third": (2, int(h * 0.2) + bar),
        "middle": (5, 0), "top": (8, int(h * 0.08) + bar),
    }.get(pos, (2, int(h * 0.07)))
    side = int(w * 0.07)
    box = bool(sub.get("box"))
    primary = _ass_color(sub["color"])
    outline_c = _ass_color(sub["outline_color"])
    back = _ass_color("#000000", float(sub.get("box_opacity", 0.55))) if box else _ass_color("#000000", 0.6)
    border_style = 3 if box else 1
    bold = -1 if sub.get("bold") else 0
    if box:
        outline_px = max(outline_px, round(size_px * 0.28, 1))
        outline_c = back  # em BorderStyle=3 a caixa usa a cor do contorno
        shadow_px = 0
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,{sub['font']},{size_px},{primary},{primary},{outline_c},{_ass_color('#000000', 0.55)},{bold},0,0,0,100,100,0,0,{border_style},{outline_px},{shadow_px},{alignment},{side},{side},{margin_v},1",
    ]
    lines += _overlay_styles(style, w, h)
    lines += ["", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    upper = bool(sub.get("uppercase"))
    anim = sub.get("animation", "none")
    hi = _ass_color(sub["highlight"])
    per = max(1, int(sub.get("words", 3)))

    def line(start: float, end: float, text: str) -> str:
        return f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"

    for cue in (cues if sub.get("enabled", True) else []):
        text = " ".join(str(cue["text"]).split())
        if upper:
            text = text.upper()
        start, end = float(cue["start"]), float(cue["end"])
        if end - start < 0.05 or not text:
            continue
        if sub.get("mode") == "word":
            words = text.split()
            weights = [len(wd) + 2 for wd in words]
            total = sum(weights)
            starts: list[float] = []
            cursor = start
            for wt in weights:
                starts.append(cursor)
                cursor += (end - start) * wt / total
            starts.append(end)
            for c0 in range(0, len(words), per):
                chunk = list(range(c0, min(c0 + per, len(words))))
                for pos_i, idx in enumerate(chunk):
                    shown = []
                    for j in chunk:
                        if j == idx:
                            extra = "\\fscx112\\fscy112" if anim == "pop" else ""
                            shown.append("{\\c" + hi + extra + "}" + _ass_text(words[j]) + "{\\r}")
                        else:
                            shown.append(_ass_text(words[j]))
                    prefix = "{\\fscx82\\fscy82\\t(0,110,\\fscx100\\fscy100)}" if (anim == "pop" and pos_i == 0) else ""
                    lines.append(line(starts[idx], starts[idx + 1], prefix + " ".join(shown)))
        else:
            prefix = ""
            if anim == "fade":
                prefix = "{\\fad(140,140)}"
            elif anim == "pop":
                prefix = "{\\fscx88\\fscy88\\t(0,120,\\fscx100\\fscy100)}"
            lines.append(line(start, end, prefix + _ass_text(text)))
    extra = _overlay_events(cues, scenes or [], style, w, h, ratio, preview)
    if preview:  # o quadro único cai em t=0: sem fade nem pop, senão sai invisível
        extra = [re.sub(r"\\fad\([^)]*\)|\\fscx60\\fscy60\\t\([^)]*\)", "", e) for e in extra]
    lines += extra
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ destaques na tela (cartões, etiquetas, barra)

_BOOKS = (r"(?:[123]\s?)?(?:Gênesis|Gênese|Êxodo|Levítico|Números|Deuteronômio|Josué|Juízes|Rute|Samuel|Reis|Crônicas|Esdras|Neemias|Ester|Jó|Salmos?|Provérbios|Eclesiastes|"
          r"Cantares|Cântico dos Cânticos|Isaías|Jeremias|Lamentações|Ezequiel|Daniel|Oseias|Oseias|Joel|Amós|Obadias|Jonas|Miqueias|Miquéias|Naum|Habacuque|Sofonias|Ageu|Zacarias|Malaquias|"
          r"Mateus|Marcos|Lucas|João|Atos|Romanos|Coríntios|Gálatas|Efésios|Filipenses|Colossenses|Tessalonicenses|Timóteo|Tito|Filemom|Hebreus|Tiago|Pedro|Judas|Apocalipse|"
          r"Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalms?|Proverbs|Isaiah|Jeremiah|Lamentations|Ezekiel|Hosea|Amos|Jonah|Micah|Nahum|"
          r"Matthew|Mark|Luke|John|Acts|Romans|Corinthians|Galatians|Ephesians|Philippians|Colossians|Thessalonians|Timothy|Hebrews|James|Peter|Jude|Revelation)")
REF_RE = re.compile(rf"\b({_BOOKS}\s+\d{{1,3}}[:.]\d{{1,3}}(?:\s?[-–]\s?\d{{1,3}})?)", re.IGNORECASE)
_STOP = set("a o as os um uma de do da dos das em no na nos nas por para com sem que e é foi são se ao aos à às mas ou como mais já só the of and to in is was for on at by an it that this".split())
# etiquetas: (x, y) da caixa e (x, y) do alvo, em % da tela
_CALLOUT_SPOTS = [(24, 30, 38, 52), (76, 28, 62, 50), (24, 68, 40, 50), (76, 66, 60, 48)]


def _accent_color(style: dict[str, Any], fallback: str = "#F59E0B") -> str:
    """Cor de destaque do estilo (cor primária validada) ou o padrão dourado."""
    cor = str(style.get("cor_primaria") or "").strip()
    return cor.upper() if _HEX.match(cor) else fallback


def _overlay_styles(style: dict[str, Any], w: int, h: int) -> list[str]:
    ov = style.get("overlays") or {}
    out: list[str] = []
    accent = _accent_color(style)
    def st(name, font, size, prim, outc, bold, ital, bs, outline, align, ml, mr, mv, back="&H00000000", spacing=0):
        return f"Style: {name},{font},{size},{prim},{prim},{outc},{back},{-1 if bold else 0},{-1 if ital else 0},0,0,100,100,{spacing},0,{bs},{outline},0,{align},{ml},{mr},{mv},1"
    if ov.get("verse_cards"):
        out.append(st("Card", "EB Garamond", max(18, int(h * 0.04)), _ass_color("#FEF3C7"), _ass_color("#000000"), False, True, 1, 0, 8, 0, 0, 0))
    if ov.get("callouts"):
        fs = max(20, int(h * 0.062))
        pad = max(6, int(h * 0.012))
        out.append(st("CallFrame", "Anton", fs, _ass_color("#000000"), _ass_color("#000000"), False, False, 3, pad + 3, 5, 0, 0, 0, spacing=1))
        out.append(st("CallPaper", "Anton", fs, _ass_color("#000000"), _ass_color("#FFFFFF"), False, False, 3, pad, 5, 0, 0, 0, spacing=1))
        out.append(st("CallYellow", "Anton", fs, _ass_color("#000000"), _ass_color(accent), False, False, 3, pad, 5, 0, 0, 0, spacing=1))
    if ov.get("topic_bar"):
        fs = max(14, int(h * 0.026))
        out.append(st("Topic", "Poppins", fs, _ass_color("#E2E8F0"), _ass_color("#000000", 0.75), True, False, 3, max(6, int(h * 0.01)), 1, int(w * 0.047), int(w * 0.3), int(h * 0.05)))
    if (style.get("cta") or {}).get("enabled"):
        fs_main = max(15, int(h * (0.032 if h > w else 0.040)))
        fs_sub = max(10, int(h * (0.017 if h > w else 0.021)))
        out.append(st("CtaMain", "Poppins", fs_main, _ass_color("#FFFFFF"), _ass_color("#000000", 0.55), True, False, 1, 0, 5, 0, 0, 0, spacing=1))
        out.append(st("CtaSub", "Poppins", fs_sub, _ass_color("#FFFFFF"), _ass_color("#000000", 0.45), False, False, 1, 0, 5, 0, 0, 0, spacing=1))
    return out


def _cta_texts(style: dict[str, Any], cues: list[dict[str, Any]] | None = None) -> tuple[str, str, str]:
    """Resolve o idioma da chamada e devolve (idioma, linha principal, linha de apoio)."""
    cta = style.get("cta") or {}
    lang = str(cta.get("language", "auto"))
    if lang not in CTA_TEXTS:
        try:
            from scenes import detect_lang
            lang = detect_lang(" ".join(str(c.get("text", "")) for c in (cues or [])[:90])) or "pt"
        except Exception:
            lang = "pt"
    main, sub = CTA_TEXTS.get(lang, CTA_TEXTS["pt"])
    override = " ".join(str(cta.get("text") or "").split())
    if override:
        if "|" in override:
            main, sub = [part.strip() for part in override.split("|", 1)]
        else:
            main = override
    return lang, main, sub


def cta_plan(style: dict[str, Any], duration: float, cues: list[dict[str, Any]] | None = None,
             *, force_position: str | None = None) -> dict[str, Any] | None:
    """Calcula quando e como a chamada de inscrição aparece no vídeo."""
    cta = style.get("cta") or {}
    if not cta.get("enabled") or duration <= 1.0:
        return None
    seconds = max(1.0, min(float(cta.get("seconds", 5.0)), max(1.0, duration - 0.4)))
    position = force_position or str(cta.get("position", "end"))
    if position not in ("start", "middle", "end"):
        position = "end"
    if position == "start":
        start = min(1.0, max(0.2, duration * 0.03))
    elif position == "middle":
        start = max(0.3, duration / 2 - seconds / 2)
    else:
        start = max(0.0, duration - seconds - 0.5)
    end = min(duration, start + seconds)
    if end - start < 1.0:
        return None
    lang, main, sub = _cta_texts(style, cues)
    palette = dict(CTA_STYLES.get(str(cta.get("style", "red")), CTA_STYLES["red"]))
    palette["accent"] = _accent_color(style, str(palette.get("accent", "#FFFFFF")))
    return {
        "start": start, "end": end, "position": position,
        "anchor": "bottom" if cta.get("anchor") == "bottom" else "top",
        "language": lang, "main": main, "sub": sub, "palette": palette,
    }


def _key_phrase(text: str) -> str:
    """Escolhe 1 a 3 palavras fortes da cena para a etiqueta (números, nomes próprios ou a palavra mais longa)."""
    words = [re.sub(r"^[^\wÀ-ÿ$%]+|[^\wÀ-ÿ$%]+$", "", x) for x in text.split()]
    words = [x for x in words if x]
    for i, x in enumerate(words):
        if re.search(r"\d", x):
            nxt = words[i + 1] if i + 1 < len(words) and words[i + 1].lower() not in _STOP else ""
            return f"{x} {nxt}".strip().upper()
    caps = [i for i, x in enumerate(words) if i > 0 and x[:1].isupper() and x.lower() not in _STOP]
    if caps:
        i = caps[0]
        j = i + 1
        while j < len(words) and j - i < 3 and words[j][:1].isupper():
            j += 1
        return " ".join(words[i:j]).upper()
    pool = [x for x in words if x.lower() not in _STOP] or words
    return max(pool, key=len).upper() if pool else ""


def _dash_line(x1: float, y1: float, x2: float, y2: float, thick: float, dash: float, gap: float) -> str:
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy * thick / 2, ux * thick / 2
    parts, d = [], 0.0
    while d < length:
        e = min(length, d + dash)
        ax, ay, bx, by = x1 + ux * d, y1 + uy * d, x1 + ux * e, y1 + uy * e
        parts.append(f"m {ax + nx:.1f} {ay + ny:.1f} l {bx + nx:.1f} {by + ny:.1f} {bx - nx:.1f} {by - ny:.1f} {ax - nx:.1f} {ay - ny:.1f}")
        d += dash + gap
    return " ".join(parts)


def _circle(cx: float, cy: float, r: float) -> str:
    k = 0.5523 * r
    return (f"m {cx - r:.1f} {cy:.1f} b {cx - r:.1f} {cy - k:.1f} {cx - k:.1f} {cy - r:.1f} {cx:.1f} {cy - r:.1f} "
            f"{cx + k:.1f} {cy - r:.1f} {cx + r:.1f} {cy - k:.1f} {cx + r:.1f} {cy:.1f} "
            f"{cx + r:.1f} {cy + k:.1f} {cx + k:.1f} {cy + r:.1f} {cx:.1f} {cy + r:.1f} "
            f"{cx - k:.1f} {cy + r:.1f} {cx - r:.1f} {cy + k:.1f} {cx - r:.1f} {cy:.1f}")


def find_verse_cards(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Acha passagens citadas (ex.: '1 Reis 11:4') e monta {ref, text, start, end} com a fala ao redor."""
    cards = []
    for i, cue in enumerate(cues):
        text = " ".join(str(cue["text"]).split())
        m = REF_RE.search(text)
        if not m:
            continue
        ref = re.sub(r"\s+", " ", m.group(1)).strip()
        ref = ref[:1].upper() + ref[1:]
        before = re.sub(r"(?:\b(?:e|mas|como)\s+)?\b(?:em|no livro de|segundo|conforme|de acordo com)\s*$", "", text[:m.start()].rstrip(), flags=re.IGNORECASE)
        quote = (before + " " + text[m.end():]).strip(" ,.;:–-()\"“”")
        quote = re.sub(r"^(?:em|no livro de|de|segundo|diz|está escrito em)\s+", "", quote, flags=re.IGNORECASE).strip(" ,.;:–-")
        end = float(cue["end"])
        if len(quote.split()) < 4 and i + 1 < len(cues):  # a citação vem na fala seguinte
            quote = " ".join(str(cues[i + 1]["text"]).split())
            end = float(cues[i + 1]["end"])
        words = quote.split()
        if len(words) > 32:
            quote = " ".join(words[:32]).rstrip(",;:") + "…"
        start = float(cue["start"])
        cards.append({"ref": ref, "text": quote, "start": start, "end": min(end, start + 9.0)})
    return cards


def _overlay_events(cues, scenes, style, w, h, ratio, preview) -> list[str]:
    ov = style.get("overlays") or {}
    ev: list[str] = []
    if ov.get("verse_cards"):
        cards = find_verse_cards(cues)
        if preview and not cards:
            cards = [{"ref": "1 Reis 11:4", "text": "Quando Salomão ficou velho, suas mulheres desviaram o seu coração para outros deuses.", "start": 0.0, "end": 6.0}]
        qfs, rfs = max(18, int(h * 0.04)), max(14, int(h * 0.03))
        for c in cards:
            card_w = int(w * (0.86 if h > w else 0.7))
            padx, pady = int(h * 0.04), int(h * 0.035)
            cpl = max(12, int((card_w - 2 * padx) / (qfs * 0.36)))
            lines_q = textwrap.wrap(c["text"], cpl) or [""]
            ref_h = int(rfs * 1.9)
            card_h = pady * 2 + ref_h + int(len(lines_q) * qfs * 1.2)
            x0, y0 = (w - card_w) // 2, max(10, (h - card_h) // 2 - int(h * 0.04))
            t0, t1 = _ass_time(c["start"]), _ass_time(c["end"])
            fade = "\\fad(250,250)"
            rect = f"m 0 0 l {card_w} 0 {card_w} {card_h} 0 {card_h}"
            ev.append(f"Dialogue: 1,{t0},{t1},Default,,0,0,0,,{{\\an7\\pos({x0},{y0}){fade}\\1c{_ass_color('#0F0A05')}\\1a&H1E&\\3c{_ass_color('#B45309')}\\bord2\\shad0\\p1}}{rect}{{\\p0}}")
            rule = f"m {padx} {pady + int(rfs * 1.5)} l {card_w - padx} {pady + int(rfs * 1.5)} {card_w - padx} {pady + int(rfs * 1.5) + 1} {padx} {pady + int(rfs * 1.5) + 1}"
            ev.append(f"Dialogue: 2,{t0},{t1},Default,,0,0,0,,{{\\an7\\pos({x0},{y0}){fade}\\1c{_ass_color('#F59E0B')}\\1a&HB0&\\bord1\\3c{_ass_color('#F59E0B')}\\shad0\\p1}}{rule}{{\\p0}}")
            ref_run = "{\\fnCinzel\\b1\\i0\\fs%d\\c%s\\fsp2}%s{\\r}" % (rfs, _ass_color("#F59E0B"), _ass_text(c["ref"].upper()))
            quote = "\\N".join(_ass_text(x) for x in lines_q)
            ref_txt = "{\\an8\\pos(%d,%d)%s}" % (w // 2, y0 + pady, fade) + ref_run
            ev.append(f"Dialogue: 3,{t0},{t1},Card,,0,0,0,,{ref_txt}")
            q_txt = "{\\an8\\pos(%d,%d)%s\\i1\\fs%d}\u201c%s\u201d" % (w // 2, y0 + pady + ref_h, fade, qfs, quote)
            ev.append(f"Dialogue: 3,{t0},{t1},Card,,0,0,0,,{q_txt}")
    if ov.get("callouts"):
        for i, sc in enumerate(scenes):
            phrase = _key_phrase(str(sc.get("text", "")))
            if not phrase:
                continue
            s0 = float(sc["render_start"]) + (0.0 if preview else 0.6)
            s1 = min(float(sc["render_end"]) - 0.3, s0 + 4.5)
            if s1 - s0 < 0.8:
                continue
            bx, by, tx, ty = _CALLOUT_SPOTS[i % len(_CALLOUT_SPOTS)]
            if ratio == "9:16":
                bx, tx = (30 if bx < 50 else 70), (45 if bx < 50 else 55)
            X1, Y1, X2, Y2 = w * bx / 100, h * by / 100, w * tx / 100, h * ty / 100
            thick = max(2.5, h * 0.004)
            draw = _dash_line(X1, Y1, X2, Y2, thick, h * 0.012, h * 0.008) + " " + _circle(X2, Y2, max(5, h * 0.009))
            ev.append(f"Dialogue: 2,{_ass_time(s0)},{_ass_time(s1)},Default,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H000000&\\fad(120,150)\\p1}}{draw}{{\\p0}}")
            yellow = bool(re.search(r"\d|\$|%", phrase))
            name = "CallYellow" if yellow else "CallPaper"
            pop = "\\fscx60\\fscy60\\t(0,220,\\fscx100\\fscy100)"
            tag = "{\\an5\\pos(%d,%d)\\frz2%s\\fad(80,120)}" % (X1, Y1, pop)
            ev.append(f"Dialogue: 4,{_ass_time(s0)},{_ass_time(s1)},CallFrame,,0,0,0,,{tag}{_ass_text(phrase)}")
            ev.append(f"Dialogue: 5,{_ass_time(s0)},{_ass_time(s1)},{name},,0,0,0,,{tag}{_ass_text(phrase)}")
    if ov.get("topic_bar"):
        for sc in scenes:
            words = " ".join(str(sc.get("text", "")).split()).split()
            topic = " ".join(words[:9]) + ("…" if len(words) > 9 else "")
            if topic:
                ev.append(f"Dialogue: 3,{_ass_time(float(sc['render_start']))},{_ass_time(float(sc['render_end']))},Topic,,0,0,0,,{{\\fad(150,150)}}{_ass_text(topic)}")
    # ---- chamada de inscrição localizada (sticker)
    total = max([float(c.get("end", 0)) for c in cues] + [float(s.get("render_end", 0)) for s in scenes] + [0.0])
    plan = cta_plan(style, 6.0 if preview else max(1.0, total), cues, force_position="start" if preview else None)
    if plan:
        if preview:
            plan["start"] = 0.0
        palette = plan["palette"]
        box_w = int(w * (0.88 if h > w else 0.66))
        box_h = int(h * (0.11 if h > w else 0.135))
        box_x = (w - box_w) // 2
        bar = int((h - w / 2.39) / 2) if (style.get("letterbox") and ratio == "16:9") else 0
        box_y = (bar + int(h * 0.035)) if plan["anchor"] == "top" else (h - bar - box_h - int(h * 0.035))
        box_y = max(int(h * 0.01), min(h - box_h - int(h * 0.01), box_y))
        radius = max(6, int(box_h * 0.18))
        accent_w = max(6, int(box_w * 0.014))
        t0, t1 = _ass_time(plan["start"]), _ass_time(plan["end"])
        fade = "\\fad(220,220)"
        bg_col = _ass_color(str(palette["back"]), float(palette.get("alpha", 0.92)))
        shadow_col = _ass_color("#000000", 0.42)
        accent_col = _ass_color(str(palette["accent"]))
        rect = f"m {radius} 0 l {box_w - radius} 0 {box_w} {radius} {box_w} {box_h - radius} {box_w - radius} {box_h} {radius} {box_h} 0 {box_h - radius} 0 {radius}"
        shadow = f"m {radius} 0 l {box_w - radius} 0 {box_w} {radius} {box_w} {box_h - radius} {box_w - radius} {box_h} {radius} {box_h} 0 {box_h - radius} 0 {radius}"
        # sombra e corpo do sticker
        ev.append(f"Dialogue: 6,{t0},{t1},Default,,0,0,0,,{{\\an7\\pos({box_x + 4},{box_y + 5}){fade}\\1c{shadow_col}\\3c{shadow_col}\\bord0\\shad0\\p1}}{shadow}{{\\p0}}")
        ev.append(f"Dialogue: 7,{t0},{t1},Default,,0,0,0,,{{\\an7\\pos({box_x},{box_y}){fade}\\1c{bg_col}\\3c{bg_col}\\bord0\\shad0\\p1}}{rect}{{\\p0}}")
        # faixa de destaque à esquerda
        ev.append(f"Dialogue: 8,{t0},{t1},Default,,0,0,0,,{{\\an7\\pos({box_x},{box_y})\\bord0\\shad0\\1c{accent_col}\\p1}}m 0 {radius} l {accent_w} {radius} {accent_w} {box_h - radius} 0 {box_h - radius}{{\\p0}}")
        main_text = _ass_text(str(plan["main"]).upper())
        sub_text = _ass_text(str(plan["sub"]))
        main_color = _ass_color(str(palette["text"]))
        sub_color = _ass_color(str(palette["sub"]))
        cx = box_x + box_w // 2 + accent_w // 2
        main_y = box_y + int(box_h * (0.40 if sub_text else 0.55))
        pop = "\\fscx92\\fscy92\\t(0,180,\\fscx100\\fscy100)"
        ev.append(f"Dialogue: 8,{t0},{t1},CtaMain,,0,0,0,,{{\\an5\\pos({cx},{main_y}){fade}{pop}\\c{main_color}}}{main_text}")
        if sub_text:
            ev.append(f"Dialogue: 8,{t0},{t1},CtaSub,,0,0,0,,{{\\an5\\pos({cx},{box_y + int(box_h * 0.72)}){fade}\\c{sub_color}}}{sub_text}")
    return ev


def has_overlays(style: dict[str, Any]) -> bool:
    return any((style.get("overlays") or {}).values()) or bool((style.get("cta") or {}).get("enabled"))


def subtitles_filter(ass_path: Path) -> str:
    return f"ass=filename='{_fq(ass_path)}':fontsdir='{_fq(FONTS_DIR)}'"


# ------------------------------------------------------------------ prévia real (mesmo filtro do render)

def render_preview(image: Path, style: dict[str, Any], ratio: str, text: str, *, key_extra: str = "") -> Path:
    """Gera um quadro JPG com o mesmo filtro e a mesma legenda usados no render."""
    w, h = ratio_dimensions(ratio, "720p")
    key = hashlib.sha1(json.dumps([str(image), image.stat().st_mtime, style, ratio, text, key_extra], sort_keys=True, default=str).encode()).hexdigest()[:20]
    out = PREVIEW_DIR / f"{key}.jpg"
    if out.exists():
        return out
    preview_style = copy.deepcopy(style)
    preview_style["subtitles"]["animation"] = "none"
    preview_style["transition"] = "cut"
    preview_style["motion"] = "none"
    chain, _ = segment_filter(preview_style, w, h, 24, 24, 0, is_image=True, first=True, last=True, ratio=ratio)
    vf = chain
    if preview_style["subtitles"].get("enabled", True) or has_overlays(preview_style):
        cues = [{"start": 0.0, "end": 6.0, "text": text}]
        ass = PREVIEW_DIR / f"{key}.ass"
        scene = [{"text": text, "render_start": 0.0, "render_end": 6.0}]
        ass.write_text(build_ass(cues, preview_style, w, h, ratio, scene, preview=True), encoding="utf-8")
        vf += "," + subtitles_filter(ass)
    cmd = [ffmpeg_path(), "-y", "-i", str(image), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    (PREVIEW_DIR / f"{key}.ass").unlink(missing_ok=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError((proc.stderr or "Falha ao gerar a prévia")[-400:])
    return out
