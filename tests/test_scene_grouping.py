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


def test_mais_de_120_cues_preserva_um_bloco_por_cena():
    cues = _many_independent_cues(131)
    scenes, capped = group_cues(cues, "slow", "pt", "", 120)
    assert capped is False
    assert len(scenes) == 131
    cue_ids = [
        int(match)
        for scene in scenes
        for match in re.findall(r"cue-(\\d{3})", scene["text"])
    ]
    assert cue_ids == list(range(131))
    assert [len(scene["source_cues"]) for scene in scenes] == [1] * 131


def test_limite_configurado_zero_nao_descarta_cues():
    scenes, capped = group_cues(_many_independent_cues(3), "slow", "pt", "", 0)
    assert capped is False
    assert len(scenes) == 3
    assert [len(scene["source_cues"]) for scene in scenes] == [1, 1, 1]


def test_quando_esta_abaixo_do_limite_mantem_cenas_originais():
    scenes, capped = group_cues(_many_independent_cues(10), "slow", "pt", "", 120)

    assert capped is False
    assert len(scenes) == 10
