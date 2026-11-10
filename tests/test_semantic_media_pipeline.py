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




def test_openrouter_localiza_trecho_do_youtube_e_aplica_limite_da_cena(monkeypatch):
    import youtube_mgr
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(youtube_mgr, "_youtube_video_duration", lambda _url: 120.0)
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        return FakeResponse({"choices": [{"message": {"content": json.dumps({
            "match": True,
            "start_seconds": 45.5,
            "end_seconds": 58.0,
            "confidence": 0.91,
            "reason": "A pessoa aparece dirigindo no trânsito.",
            "visual_summary": "Carro em movimento numa avenida.",
        }, ensure_ascii=False)}}]})

    monkeypatch.setattr(youtube_mgr.requests, "post", fake_post)
    result = youtube_mgr.locate_youtube_moment(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "Ele finalmente dirige o carro que comprou.",
        model="google/gemini-2.5-flash",
        max_seconds=8,
    )
    video_part = captured["payload"]["messages"][0]["content"][1]
    assert captured["url"].endswith("/chat/completions")
    assert video_part["type"] == "video_url"
    assert video_part["video_url"]["processing"] == "agentic"
    assert result["start_seconds"] == 45.5
    assert result["end_seconds"] == 53.5
    assert result["duration"] == 8.0
    assert result["confidence"] == 0.91


def test_openrouter_locator_rejeita_video_sem_cena_compativel(monkeypatch):
    import pytest
    import youtube_mgr
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(youtube_mgr, "_youtube_video_duration", lambda _url: 80.0)

    def fake_post(_url, **_kwargs):
        return FakeResponse({"choices": [{"message": {"content": json.dumps({
            "match": False,
            "reason": "O vídeo não mostra a ação narrada.",
        }, ensure_ascii=False)}}]})

    monkeypatch.setattr(youtube_mgr.requests, "post", fake_post)
    with pytest.raises(RuntimeError, match="não mostra a ação"):
        youtube_mgr.locate_youtube_moment(
            "https://youtu.be/abcdefghijk",
            "A fala descreve uma fábrica.",
            max_seconds=10,
        )




def test_auto_pick_nao_seleciona_candidato_youtube_sem_extracao(monkeypatch):
    import scenes as scene_tools
    planned = [{
        "id": "scene_1",
        "start": 0.0,
        "end": 7.0,
        "options": [{
            "id": "yt_candidate",
            "provider": "YouTube",
            "media_type": "video",
            "preview_only": True,
        }],
    }]

    scene_tools.auto_pick(planned, "mixed", "16:9", video_percent=100)

    assert planned[0]["selected"] == -1

def test_stock_only_mantem_youtube_como_fonte_real_e_separa_modelo_de_visao(monkeypatch):
    import main
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    cfg = main.normalize_settings({
        "sources": ["youtube_video", "youtube_frame", "wikimedia_video", "openverse_image"],
        "stock_only": True,
        "openrouter_model": "google/gemini-2.5-flash",
        "openrouter_vision_model": "google/gemini-2.5-flash",
    })
    assert "youtube_video" in cfg["sources"]
    assert "wikimedia_video" in cfg["sources"]
    assert "openverse_image" in cfg["sources"]
    assert cfg["stock_only"] is True
    assert cfg["semantic_scene_grouping"] is True
    assert cfg["openrouter_vision_model"] == "google/gemini-2.5-flash"



def test_scene_preserva_cada_cue_original_com_timestamps():
    from scenes import parse_srt, _scene
    cues = parse_srt(SRT)
    scene = _scene(cues[:2], 1, "pt", "")
    assert len(scene["source_cues"]) == 2
    assert scene["source_cues"][0] == {
        "id": "cue-0001", "start": 0.0, "end": 2.0,
        "text": "Ele trabalhou durante anos na fábrica.",
    }
    assert scene["source_cues"][1]["start"] == 2.0
    assert scene["source_cues"][1]["end"] == 4.0


def test_parser_preserva_planos_visuais_individuais_por_cue():
    import scene_planner
    parsed = scene_planner._parse_json_plan(json.dumps({
        "consultas": ["São Paulo 1970 aerial footage"],
        "cue_plans": [{
            "cue_id": "cue-0001",
            "consultas": ["São Paulo 1970 street archive"],
            "descricao_visual": "Ruas de São Paulo na década de 1970",
            "recommended_media": "video",
            "motion_score": 88,
        }],
    }, ensure_ascii=False))
    assert parsed["cue_plans"][0]["cue_id"] == "cue-0001"
    assert parsed["cue_plans"][0]["consultas"] == ["São Paulo 1970 street archive"]
    assert parsed["cue_plans"][0]["motion_score"] == 88
