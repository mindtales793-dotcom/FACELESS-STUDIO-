"""Testes dos bancos alternativos de mídia."""
from __future__ import annotations

import providers


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_prelinger_exige_licenca_reutilizavel_e_exclui_nc(monkeypatch):
    monkeypatch.setattr(providers, "_cache_read", lambda _key: None)
    monkeypatch.setattr(providers, "_cache_write", lambda *_args: None)
    payloads = [
        {"response": {"docs": [
            {"identifier": "film-ok", "title": "Factory film"},
            {"identifier": "film-nc", "title": "Noncommercial film"},
            {"identifier": "film-no-license", "title": "Unknown rights"},
        ]}},
        {"metadata": {
            "title": "Factory film", "creator": "Prelinger",
            "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
            "length": "42.5",
        }, "files": [{"name": "factory.mp4", "height": "720", "width": "1280", "size": "1000"}]},
        {"metadata": {
            "title": "Noncommercial film",
            "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/",
        }, "files": [{"name": "noncommercial.mp4", "height": "720", "size": "1000"}]},
        {"metadata": {"title": "Unknown rights"}, "files": [
            {"name": "unknown.mp4", "height": "720", "size": "1000"}]},
    ]
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        return FakeResponse(payloads.pop(0))

    monkeypatch.setattr(providers.requests, "get", fake_get)
    result = providers.prelinger_search("factory", 3)

    assert len(result) == 1
    assert result[0]["provider"] == "Prelinger Archives"
    assert result[0]["media_type"] == "video"
    assert result[0]["license"].endswith("/by/4.0/")
    assert result[0]["download_url"].endswith("/film-ok/factory.mp4")
    assert len(calls) == 4


def test_catalogo_de_fontes_externas_tem_busca_e_licenca():
    sources = providers.public_external_sources()
    ids = {source["id"] for source in sources}
    assert {"videezy_external", "vecteezy_external", "dareful_external",
            "lifeofvids_external", "stocksnap_external", "isorepublic_external",
            "kaboompics_external", "burst_external"} <= ids
    assert all(source["search_prefix"].startswith("https://www.google.com/search?q=") for source in sources)
    assert all(source.get("license") and source.get("link") for source in sources)
