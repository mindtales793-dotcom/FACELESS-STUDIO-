"""Regressões para falhas de cobrança do OpenRouter durante buscas longas."""

def test_openrouter_402_desativa_novas_chamadas_na_mesma_busca(monkeypatch):
    import scene_planner

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = scene_planner.requests.Response()
    response.status_code = 402
    response.url = "https://openrouter.ai/api/v1/chat/completions"
    error = scene_planner.requests.HTTPError(
        "402 Client Error: Payment Required", response=response
    )
    calls = []

    def fail_with_payment_required(*_args, **_kwargs):
        calls.append(True)
        raise error

    monkeypatch.setattr(scene_planner, "_openrouter_plan", fail_with_payment_required)

    first = scene_planner.gerar_consultas_para_cena(
        "A cidade crescia e recebia novos moradores.",
        idioma="pt",
    )
    second = scene_planner.gerar_consultas_para_cena(
        "As fábricas se espalhavam pela região.",
        idioma="pt",
        usar_openrouter=False,
    )

    assert first["provider"] == "fallback"
    assert first["openrouter_quota_exhausted"] is True
    assert "402" in first["fallback_reason"]
    assert second["provider"] == "fallback"
    assert second["openrouter_quota_exhausted"] is True
    assert len(calls) == 1


def test_verificacao_visual_pula_openrouter_depois_do_402(monkeypatch):
    import media_relevance

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    calls = []

    def unexpected_request(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("Não deveria enviar outra chamada ao OpenRouter.")

    monkeypatch.setattr(media_relevance.requests, "post", unexpected_request)
    candidates = [{
        "provider": "Pexels",
        "media_type": "image",
        "thumbnail": "https://example.com/thumb.jpg",
    }]

    kept, report = media_relevance.verify_scene_candidates(
        scene_text="Uma fábrica na cidade.",
        candidates=candidates,
        disable_openrouter=True,
    )

    assert kept == candidates
    assert report["status"] == "unavailable"
    assert report["quota_exhausted"] is True
    assert calls == []


def test_verificacao_visual_identifica_http_402(monkeypatch):
    import media_relevance

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    response = media_relevance.requests.Response()
    response.status_code = 402
    response.url = media_relevance.OPENROUTER_URL
    monkeypatch.setattr(media_relevance.requests, "post", lambda *_args, **_kwargs: response)
    candidates = [{
        "provider": "Pexels",
        "media_type": "image",
        "thumbnail": "https://example.com/thumb.jpg",
    }]

    kept, report = media_relevance.verify_scene_candidates(
        scene_text="Uma fábrica na cidade.",
        candidates=candidates,
    )

    assert kept == candidates
    assert report["status"] == "unavailable"
    assert report["quota_exhausted"] is True
    assert "402" in report["message"]


def test_openrouter_planejador_forca_roteador_free_mesmo_com_modelo_pago(monkeypatch):
    import scene_planner
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    captured = {}
    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": [{"message": {"content": '{"consultas":["factory workers"]}'}}]}
    def fake_post(_url, **kwargs):
        captured.update(kwargs.get("json") or {})
        return FakeResponse()
    monkeypatch.setattr(scene_planner.requests, "post", fake_post)
    scene_planner._openrouter_plan("prompt", model="provider/model-pago")
    assert captured["model"] == "openrouter/free"


def test_planejamento_free_nao_chama_gemini_quando_desativado(monkeypatch):
    import scene_planner
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    def fail_openrouter(*_args, **_kwargs):
        raise RuntimeError("modelo free indisponível")
    def fail_gemini(*_args, **_kwargs):
        raise AssertionError("Não pode chamar Gemini neste modo.")
    monkeypatch.setattr(scene_planner, "_openrouter_plan", fail_openrouter)
    monkeypatch.setattr(scene_planner.requests, "post", fail_gemini)
    result = scene_planner.gerar_consultas_para_cena(
        "Uma fábrica no centro da cidade.", usar_openrouter=True, usar_gemini=False,
        cue_texts=[{"id":"c1","text":"Uma fábrica no centro da cidade."}],
    )
    assert result["provider"] == "fallback"
    assert result["cue_plans"][0]["cue_id"] == "c1"
