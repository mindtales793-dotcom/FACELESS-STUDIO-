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
