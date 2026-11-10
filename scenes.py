"""Leitura de SRT, divisão em cenas, consulta de busca e escolha automática de mídia."""
from __future__ import annotations

import math
import re
import time
from typing import Any

from styles import PACING

PT_STOP = set(
    "a o as os um uma uns umas de da do das dos em no na nos nas para por com sem sobre entre ao aos à às e ou mas que se sua seu suas seus ele ela eles elas isso este esta esse essa aquele aquela como quando onde porque então muito mais menos ser estar ter haver foi são era eram sendo está estão estavam pode podem deve devem você voces nós meu minha nosso nossa pelo pela pelos pelas depois antes durante também já ainda cada todo toda todos todas mesmo mesma vida mundo pessoa pessoas coisa coisas algo alguém aquilo aqui ali lá".split()
)
EN_STOP = set(
    "the a an and or but of to in on at for with without from by about as is are was were be been being it its this that these those he she they them his her their we you your i my our not no so if then than also just very more most such can could will would should may might do does did done have has had having into over under again further once here there when where why how all any both each few other some own same too now what which who whom while because after before during until through between against out up down off".split()
)
PT_ONLY = {"que", "não", "uma", "com", "para", "por", "mas", "foi", "são", "está", "você", "isso", "também", "já", "muito", "ele", "ela", "dos", "das", "nos", "nas", "mais", "como", "quando", "então", "depois"}
EN_ONLY = {"the", "and", "was", "were", "with", "that", "this", "they", "you", "for", "have", "had", "not", "but", "his", "her", "from", "which", "their", "would", "been", "into", "what", "when"}


def detect_lang(text: str) -> str:
    words = re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower())
    pt = sum(1 for w in words if w in PT_ONLY)
    en = sum(1 for w in words if w in EN_ONLY)
    return "en" if en > pt else "pt"


def parse_srt(text: str) -> list[dict[str, Any]]:
    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues: list[dict[str, Any]] = []
    pattern = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})")

    def to_seconds(value: str) -> float:
        hh, mm, rest = value.replace(",", ".").split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(rest)

    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        match = pattern.search("\n".join(lines))
        if not match:
            continue
        timing_line = next(i for i, line in enumerate(lines) if "-->" in line)
        cue_text = " ".join(lines[timing_line + 1:]).strip()
        cue_text = re.sub(r"<[^>]+>", "", cue_text)
        cue_text = re.sub(r"\{\\an\d+\}", "", cue_text)
        if not cue_text:
            continue
        start, end = to_seconds(match.group("start")), to_seconds(match.group("end"))
        if end > start:
            cues.append({"start": start, "end": end, "text": cue_text})
    cues.sort(key=lambda c: (c["start"], c["end"]))
    if not cues:
        raise ValueError("O arquivo SRT não contém legendas válidas. Confira o formato e os horários.")
    return cues


def _translate_to_en(text: str) -> str:
    """Traduz texto para inglês usando o endpoint gratuito do Google Translate.

    A tradução é opcional: se a rede estiver bloqueada ou lenta, a busca usa o
    texto original. Depois da primeira falha, o app fica 10 minutos sem tentar
    de novo, para não travar a criação de projetos cena por cena.
    """
    global _TRANSLATION_OFF_UNTIL
    key = " ".join(text.lower().split())[:220]
    if key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[key]
    if time.monotonic() < _TRANSLATION_OFF_UNTIL:
        return text
    now = time.monotonic()
    if now >= _TRANSLATION_WINDOW["reset"]:
        _TRANSLATION_WINDOW["left"] = 12
        _TRANSLATION_WINDOW["reset"] = now + 60
    if _TRANSLATION_WINDOW["left"] <= 0:
        return text
    _TRANSLATION_WINDOW["left"] -= 1
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        q = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = _json.loads(r.read())
            parts = data[0]
            result = " ".join(p[0] for p in parts if p and p[0]).strip()
            if result:
                if len(_TRANSLATION_CACHE) > 600:
                    _TRANSLATION_CACHE.clear()
                _TRANSLATION_CACHE[key] = result
            return result
    except Exception:
        _TRANSLATION_OFF_UNTIL = time.monotonic() + 600
        return text


# Cache de traduções: evita repetir a mesma chamada em cenas parecidas.
_TRANSLATION_CACHE: dict[str, str] = {}
_TRANSLATION_OFF_UNTIL = 0.0
# Orçamento de rede: no máximo 12 traduções por minuto, para a criação de
# projetos longos não ficar esperando o tradutor cena por cena.
_TRANSLATION_WINDOW: dict[str, float] = {"left": 12, "reset": 0.0}

# Mapa de conceitos visuais. Ajuda a busca a sair do literal ("dinheiro" não vira
# apenas "money": vira "money finance cash", que rende clipes melhores).
_CONCEPT_MAP: dict[str, str] = {
    "dinheiro": "money finance cash", "rico": "wealth luxury", "riqueza": "wealth luxury",
    "pobreza": "poverty slum", "banco": "bank finance", "mercado": "stock market finance",
    "bolsa": "stock market trading", "investimento": "investment finance", "economia": "economy business",
    "empresa": "corporate business office", "trabalho": "workers workplace", "fábrica": "factory industry",
    "cidade": "city skyline street", "rua": "street city", "campo": "countryside field", "floresta": "forest trees",
    "mar": "ocean sea waves", "oceano": "ocean waves", "deserto": "desert dunes", "montanha": "mountain landscape",
    "chuva": "rain storm", "tempestade": "storm lightning", "noite": "night darkness", "lua": "moon night sky",
    "sol": "sunlight sunset", "espaço": "space galaxy", "planeta": "planet space", "terra": "earth planet",
    "guerra": "war soldiers", "exército": "army soldiers", "soldado": "soldier war", "arma": "weapon gun",
    "crime": "crime police investigation", "polícia": "police officers", "prisão": "prison jail", "tribunal": "courtroom judge",
    "política": "politician government", "protesto": "protest crowd", "multidão": "crowd people", "povo": "people crowd",
    "igreja": "church cathedral", "bíblia": "bible ancient book", "rei": "king crown royal", "rainha": "queen crown royal",
    "história": "history ancient archive", "antigo": "ancient ruins", "arqueologia": "archaeology ruins",
    "tecnologia": "technology computer", "computador": "computer technology", "internet": "internet network",
    "celular": "smartphone phone", "inteligência": "artificial intelligence", "robô": "robot artificial intelligence",
    "ciência": "science laboratory", "médico": "doctor hospital", "hospital": "hospital medical", "remédio": "medicine pills",
    "doença": "disease medical", "família": "family home", "criança": "child kids", "mulher": "woman portrait",
    "homem": "man portrait", "casa": "house home", "carro": "car driving", "avião": "airplane flight",
    "navio": "ship ocean", "trem": "train railway", "fogo": "fire flames", "água": "water", "comida": "food cooking",
    "religião": "religion faith", "medo": "fear dark", "morte": "dark cemetery", "amor": "love couple",
    "sucesso": "success achievement", "fracasso": "failure struggle", "sonho": "dream surreal",
    "money": "money finance cash", "wealth": "wealth luxury", "city": "city skyline street",
    "war": "war soldiers", "crime": "crime police investigation", "police": "police officers",
    "technology": "technology computer", "ai": "artificial intelligence", "history": "history ancient archive",
    "ancient": "ancient ruins", "ocean": "ocean waves", "forest": "forest trees", "desert": "desert dunes",
    "space": "space galaxy", "night": "night darkness", "storm": "storm lightning", "church": "church cathedral",
    "bible": "bible ancient book", "king": "king crown royal", "queen": "queen crown royal", "family": "family home",
    "child": "child kids", "woman": "woman portrait", "man": "man portrait", "car": "car driving",
    "airplane": "airplane flight", "ship": "ship ocean", "train": "train railway", "fire": "fire flames",
    "food": "food cooking", "death": "dark cemetery", "love": "love couple", "dream": "dream surreal",
}


def query_variants(text: str, lang: str = "auto", extra: str = "", limit: int = 3) -> list[str]:
    """Gera variantes de busca: principal, curta e ampla (para quando o banco devolve pouco)."""
    primary = make_query(text, lang, extra)
    words = primary.split()
    variants: list[str] = [primary]
    if len(words) > 3:
        variants.append(" ".join(words[:3]))
    if len(words) > 2:
        broad = " ".join(words[:2]) + " cinematic documentary footage"
        variants.append(broad)
    extra_clean = " ".join(extra.split())[:60]
    if extra_clean and extra_clean.lower() not in primary.lower():
        variants.append((primary + " " + extra_clean).strip())
    out: list[str] = []
    seen: set[str] = set()
    for value in variants:
        clean = " ".join(value.split()).strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            out.append(clean)
        if len(out) >= max(1, min(4, limit)):
            break
    return out


# Palavras que não têm valor visual em buscas de stock/b-roll — além dos stopwords
_VISUAL_NOISE = {
    # verbos abstratos (PT)
    "descobrir", "perceber", "entender", "saber", "pensar", "acreditar", "imaginar",
    "dizer", "falar", "contar", "explicar", "mostrar", "ver", "ouvir", "sentir",
    "começar", "continuar", "terminar", "acontecer", "parecer", "tornar",
    "cruzar", "passar", "chegar", "sair", "voltar", "ficar", "ser", "estar", "ter",
    "ninguem", "alguem", "nenhum", "nenhuma", "qualquer", "qualquer",
    # verbos abstratos (EN)
    "discover", "realize", "realise", "understand", "know", "think", "believe",
    "imagine", "say", "tell", "explain", "show", "see", "hear", "feel",
    "begin", "continue", "finish", "happen", "seem", "become", "cross", "pass",
    "arrive", "leave", "return", "stay", "nobody", "someone", "anyone",
    "nothing", "something", "anything", "everything",
    # advérbios/quantificadores sem imagem (PT)
    "muito", "pouco", "tanto", "quanto", "quase", "apenas", "somente",
    "primeiro", "segundo", "terceiro", "último", "próximo", "anterior",
    # advérbios/quantificadores sem imagem (EN)
    "very", "much", "little", "almost", "only", "just", "quite", "enough",
    "first", "second", "third", "last", "next", "previous", "gentle", "brutal",
    # pronomes e conectivos abstratos
    "isso", "aquilo", "este", "esse", "aquele", "tal", "cada", "todo",
    "this", "that", "such", "each", "every", "those", "these",
}


def make_query(text: str, lang: str = "auto", extra: str = "") -> str:
    """Gera uma query de busca visual em inglês a partir do texto da cena.

    Para canais faceless: extrai substantivos/adjetivos concretos que descrevem
    imagens reais, traduz PT→EN e devolve uma query limpa para bancos de stock.
    """
    clean = re.sub(r"https?://\S+", "", text.lower())
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", clean)
    if lang == "auto":
        lang = detect_lang(text)
    stop = EN_STOP if lang == "en" else PT_STOP

    # Remove stopwords + palavras sem valor visual
    useful = [w for w in words if w not in stop and w not in _VISUAL_NOISE and len(w) > 2]
    if not useful:
        # Fallback progressivo
        useful = [w for w in words if w not in stop and len(w) > 2] or \
                 [w for w in words if len(w) > 2] or words

    # Prioriza palavras mais longas (substantivos/adjetivos concretos tendem a ser mais longos)
    useful_sorted = sorted(useful, key=lambda w: (-len(w), useful.index(w)))
    keywords = useful_sorted[:7]
    query_raw = " ".join(keywords)

    # Se o texto é português, traduz para inglês — bancos stock retornam muito mais
    if lang == "pt" and query_raw:
        translated = _translate_to_en(query_raw)
        if translated and len(translated) > 3:
            query_raw = translated

    # Aplica o mapa de conceitos visuais (dinheiro -> money finance cash, etc.)
    mapped: list[str] = []
    for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", query_raw):
        low = token.lower()
        if low in EN_STOP or low in PT_STOP or len(low) < 2:
            continue
        phrase = _CONCEPT_MAP.get(low, token)
        for piece in phrase.split():
            if piece.lower() not in EN_STOP and piece not in mapped:
                mapped.append(piece)
    if mapped:
        query_raw = " ".join(mapped[:6])

    # Limpa espaços extras
    query_clean = re.sub(r"\s+", " ", query_raw).strip()
    if not query_clean:
        query_clean = "cinematic documentary footage"

    extra_clean = " ".join(extra.split())[:60]
    return f"{query_clean} {extra_clean}".strip()


def make_youtube_query(text: str, lang: str = "auto", extra: str = "") -> str:
    """Versão da query otimizada para busca no YouTube b-roll.

    Mantém só as 3 palavras-chave mais concretas + sufixo de footage.
    Menos palavras = YouTube acha clipes mais relevantes.
    """
    base = make_query(text, lang, extra)
    # Pega só as primeiras 3 palavras da query traduzida (mais específico no YouTube)
    core = " ".join(base.split()[:3])
    return core if core else "cinematic nature documentary"


def _scene(cues: list[dict[str, Any]], number: int, lang: str, extra: str) -> dict[str, Any]:
    text = " ".join(c["text"] for c in cues)
    query = make_query(text, lang, extra)
    return {
        "id": f"scene-{number:03d}", "start": cues[0]["start"], "end": cues[-1]["end"],
        "text": text[:1200], "query": query,
        "search_queries": query_variants(text, lang, extra, 3),
        "search_notes": [],
        "options": [], "selected": 0, "status": "pending",
    }


def _fit_groups_to_limit(groups: list[list[dict[str, Any]]], max_scenes: int) -> list[list[dict[str, Any]]]:
    """Reduz a quantidade de grupos com o mínimo de junções e sem perder a ordem.

    Distribui os grupos originais em blocos contíguos e equilibrados. Ex.: 131
    grupos com limite 120 viram 11 cenas com dois grupos e 109 com um grupo,
    em vez de juntar tudo em pares e reduzir a quantidade praticamente pela metade.
    """
    total = len(groups)
    try:
        limit = max(1, int(max_scenes))
    except (TypeError, ValueError):
        limit = 120
    if total <= limit:
        return groups

    fitted: list[list[dict[str, Any]]] = []
    start = 0
    for index in range(limit):
        # Arredondamento inteiro distribui as junções pelo vídeo, evitando
        # concentrar todas as cenas maiores no começo ou no final.
        end = ((index + 1) * total + limit // 2) // limit
        end = max(start + 1, end)
        # Reserva ao menos um grupo para cada cena que ainda falta criar.
        end = min(end, total - (limit - index - 1))
        merged: list[dict[str, Any]] = []
        for group in groups[start:end]:
            merged.extend(group)
        fitted.append(merged)
        start = end

    return fitted


def group_cues(cues: list[dict[str, Any]], pacing: str, lang: str, extra: str, max_scenes: int) -> tuple[list[dict[str, Any]], bool]:
    """Agrupa legendas em cenas conforme o ritmo. Retorna (cenas, ritmo_foi_limitado)."""
    rule = PACING.get(pacing, PACING["balanced"])
    max_span, max_words = rule["span"], rule["words"]
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    group_start = 0.0
    for cue in cues:
        if not current:
            current, group_start = [cue], cue["start"]
            continue
        words = sum(len(c["text"].split()) for c in current)
        if cue["end"] - group_start > max_span or words + len(cue["text"].split()) > max_words:
            groups.append(current)
            current, group_start = [cue], cue["start"]
        else:
            current.append(cue)
    if current:
        groups.append(current)

    try:
        scene_limit = max(1, int(max_scenes))
    except (TypeError, ValueError):
        scene_limit = 120
    capped = len(groups) > scene_limit
    if capped:
        groups = _fit_groups_to_limit(groups, scene_limit)
    return [_scene(g, n + 1, lang, extra) for n, g in enumerate(groups)], capped


def _quality_score(option: dict[str, Any]) -> float:
    """Nota de qualidade técnica e de relevância devolvida pelos bancos."""
    w, h = int(option.get("width") or 0), int(option.get("height") or 0)
    short = min(w, h) if w and h else 0
    score = 0.0
    if short >= 2160:
        score += 3.0
    elif short >= 1080:
        score += 2.4
    elif short >= 720:
        score += 1.6
    elif short >= 480:
        score += 0.8
    rel = option.get("relevance")
    if isinstance(rel, (int, float)):
        score += max(0.0, min(1.0, float(rel))) * 3.5
    downloads = option.get("downloads") or option.get("likes") or option.get("views")
    if isinstance(downloads, (int, float)) and downloads > 0:
        score += min(2.0, math.log10(float(downloads) + 1) * 0.45)
    return score


def assign_media_targets(scenes: list[dict[str, Any]], video_percent: int = 50) -> None:
    """Distribui a cota de vídeos entre as cenas, priorizando as que precisam de movimento."""
    try:
        percent = max(0, min(100, int(video_percent)))
    except (TypeError, ValueError):
        percent = 50
    total = len(scenes)
    video_count = int(total * percent / 100 + 0.5)
    ranked = sorted(
        range(total),
        key=lambda idx: (
            float(scenes[idx].get("motion_score", 50) or 50),
            1 if scenes[idx].get("recommended_media") == "video" else 0,
            -idx,
        ),
        reverse=True,
    )
    video_ids = set(ranked[:video_count])
    for idx, scene in enumerate(scenes):
        scene["target_media_type"] = "video" if idx in video_ids else "image"


def auto_pick(scenes: list[dict[str, Any]], pref: str, ratio: str, video_percent: int = 50) -> None:
    """Escolhe mídia sem repetição, respeitando a cota imagem/vídeo quando há opções disponíveis."""
    assign_media_targets(scenes, video_percent)
    used: set[tuple[Any, Any]] = set()
    provider_use: dict[str, int] = {}
    want_landscape = ratio != "9:16"
    for scene in scenes:
        options = scene.get("options") or []
        if not options:
            continue
        usable = [(i, option) for i, option in enumerate(options) if not option.get("preview_only")]
        if not usable:
            # Candidatos do YouTube precisam passar pela extração autorizada antes do render.
            scene["selected"] = -1
            scene["media_target_fallback"] = True
            continue
        dur = max(0.5, float(scene["end"]) - float(scene["start"]))
        target = scene.get("target_media_type")
        preferred = [(i, option) for i, option in usable if option.get("media_type") == target]
        # Não deixa uma cena sem mídia se a cota escolhida não existe nos bancos marcados.
        candidates = preferred or usable
        scene["media_target_fallback"] = not bool(preferred)
        best_i, best_score = candidates[0][0], -1e9
        for i, option in candidates:
            score = -i * 0.02
            key = (option.get("provider"), option.get("id"))
            if key in used:
                score -= 120
            if option.get("local_file"):
                score += 60
            if pref in ("video", "image"):
                score += 2 if option.get("media_type") == pref else -0.5
            if option.get("media_type") == "video":
                d = float(option.get("duration") or 0)
                if d >= dur:
                    score += 5
                elif d > 0:
                    score += 4 * d / dur
                else:
                    score -= 1
                if d and d < 2.0:
                    score -= 2
            w, h = option.get("width"), option.get("height")
            if w and h:
                if (w >= h) == want_landscape:
                    score += 3
                else:
                    score -= 2.5
            score += _quality_score(option)
            score -= min(3.0, provider_use.get(str(option.get("provider")), 0) * 0.35)
            if score > best_score:
                best_i, best_score = i, score
        scene["selected"] = best_i
        chosen = options[best_i]
        used.add((chosen.get("provider"), chosen.get("id")))
        provider = str(chosen.get("provider"))
        provider_use[provider] = provider_use.get(provider, 0) + 1
