"""Regressões para o agrupamento de legendas em cenas."""
from __future__ import annotations

import re

from scenes import group_cues


def _many_independent_cues(count: int) -> list[dict[str, object]]:
    # 38 palavras por bloco força cada legenda a iniciar um novo grupo no
    # ritmo lento, tornando previsível a quantidade antes do limite global.
    filler = " ".join(["palavra"] * 37)
    return [
        {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"cue-{i:03d} {filler}"}
        for i in range(count)
    ]


def test_limite_120_faz_apenas_as_juncoes_necessarias_e_preserva_todos_os_blocos():
    cues = _many_independent_cues(131)

    scenes, capped = group_cues(cues, "slow", "pt", "", 120)

    assert capped is True
    assert len(scenes) == 120
    cue_ids = [
        int(match)
        for scene in scenes
        for match in re.findall(r"cue-(\\d{3})", scene["text"])
    ]
    assert cue_ids == list(range(131))

    # 131 grupos -> 120 cenas: são necessárias exatamente 11 junções.
    sizes = [len(re.findall(r"cue-\\d{3}", scene["text"])) for scene in scenes]
    assert sizes.count(2) == 11
    assert sizes.count(1) == 109
    assert max(sizes) == 2


def test_limite_configurado_zero_nao_quebra_a_divisao():
    scenes, capped = group_cues(_many_independent_cues(3), "slow", "pt", "", 0)

    assert capped is True
    assert len(scenes) == 1
    assert len(re.findall(r"cue-\\d{3}", scenes[0]["text"])) == 3


def test_quando_esta_abaixo_do_limite_mantem_cenas_originais():
    scenes, capped = group_cues(_many_independent_cues(10), "slow", "pt", "", 120)

    assert capped is False
    assert len(scenes) == 10
