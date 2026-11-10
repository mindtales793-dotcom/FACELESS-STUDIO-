"""Testes do pipeline de cenas semânticas e mídia stock real."""
from __future__ import annotations

import json


SRT = """1
00:00:00,000 --> 00:00:02,000
Ele trabalhou durante anos na fábrica.

2
00:00:02,000 --> 00:00:04,000
Todos os dias, economizava uma parte do salário.

3
00:00:04,000 --> 00:00:06,000
Até que finalmente comprou seu primeiro carro.
"""


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_openrouter_agrupa_cues_por_significado_sem_alterar_tempo_ou_fala(monkeypatch):
    import scene_planner
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return FakeResponse({
            "choices": [{
                "message": {
                    "content": json.dumps({"scene_ends": [1, 2]}, ensure_ascii=False)
                }
            }]
        })

    monkeypatch.setattr(scene_planner.requests, "post", fake_post)
    scenes, capped, report = scene_planner.agrupar_cenas_por_significado(
        SRT, ritmo="balanced", idioma="pt", max_cenas=20,
        model="google/gemini-2.5-flash",
    )

    assert report["provider"] == "openrouter"
    assert capped is False
    assert len(scenes) == 2
    assert scenes[0]["start"] == 0
    assert scenes[0]["end"] == 4
    assert "Ele trabalhou durante anos na fábrica." in scenes[0]["text"]
    assert "economizava uma parte do salário." in scenes[0]["text"]
    assert scenes[1]["start"] == 4
    assert scenes[1]["end"] == 6
    assert scenes[1]["text"] == "Até que finalmente comprou seu primeiro carro."
    assert captured["url"].endswith("/chat/completions")


def test_openrouter_agrupamento_invalido_usa_fallback_sem_perder_cues(monkeypatch):
    import scene_planner
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def fake_post(_url, **_kwargs):
        return FakeResponse({"choices": [{"message": {"content": '{"scene_ends":[1]}'}}]})

    monkeypatch.setattr(scene_planner.requests, "post", fake_post)
    scenes, _capped, report = scene_planner.agrupar_cenas_por_significado(
        SRT, ritmo="balanced", idioma="pt", max_cenas=20,
    )

    assert report["provider"] == "temporal_fallback"
    assert len(scenes) >= 1
    assert "Ele trabalhou" in " ".join(scene["text"] for scene in scenes)
    assert "comprou seu primeiro carro" in " ".join(scene["text"] for scene in scenes)


def test_sem_openrouter_usa_agrupamento_temporal(monkeypatch):
    import scene_planner
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    scenes, _capped, report = scene_planner.agrupar_cenas_por_significado(
        SRT, ritmo="balanced", idioma="pt", max_cenas=20,
    )
    assert report["provider"] == "temporal_fallback"
    assert len(scenes) >= 1


def test_stock_only_remove_youtube_e_separa_modelo_de_visao(monkeypatch):
    import main
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    cfg = main.normalize_settings({
        "sources": ["youtube_video", "youtube_frame", "wikimedia_video", "openverse_image"],
        "stock_only": True,
        "openrouter_model": "google/gemini-2.5-flash",
        "openrouter_vision_model": "google/gemini-2.5-flash",
    })
    assert "youtube_video" not in cfg["sources"]
    assert "youtube_frame" not in cfg["sources"]
    assert "wikimedia_video" in cfg["sources"]
    assert "openverse_image" in cfg["sources"]
    assert cfg["stock_only"] is True
    assert cfg["semantic_scene_grouping"] is True
    assert cfg["openrouter_vision_model"] == "google/gemini-2.5-flash"
