"""Testes de regressão dos bugs corrigidos. Rodar com: python -m pytest tests -q"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pasta de dados isolada: o store lê DATA_DIR na importação.
_TMP = tempfile.mkdtemp(prefix="fcs_test_")
os.environ["DATA_DIR"] = _TMP
os.environ.pop("APP_PASSWORD", None)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import scene_planner  # noqa: E402

SRT = """1
00:00:00,000 --> 00:00:03,000
Primeira frase do roteiro.

2
00:00:03,000 --> 00:00:06,500
Segunda frase do roteiro.
"""


@pytest.fixture()
def client():
    main._LOGIN_FAILS.clear()
    return TestClient(main.app)


# ------------------------------------------------------------------ planejador de cenas
def test_planejar_cenas_sem_llm():
    cenas = scene_planner.planejar_cenas(SRT, usar_llm=False)
    assert len(cenas) == 2
    assert all(c["consultas"] and c["status"] == "pendente" for c in cenas)


def test_planejar_cenas_com_llm_respeita_max_consultas(monkeypatch):
    # Antes: NameError ('max_consultas' não existia) sempre que usar_llm=True.
    monkeypatch.setattr(
        scene_planner, "gerar_consultas_para_cena",
        lambda texto, idioma="auto", max_consultas=4: {
            "palavras_chave": ["a"], "consultas": ["q1", "q2", "q3", "q4"], "descricao_visual": "x"},
    )
    cenas = scene_planner.planejar_cenas(SRT, idioma="en", usar_llm=True, max_consultas=2)
    assert [c["consultas"] for c in cenas] == [["q1", "q2"], ["q1", "q2"]]


# ------------------------------------------------------------------ path traversal
def test_safe_child_bloqueia_saida_da_pasta(tmp_path):
    pasta = tmp_path / "pub"
    pasta.mkdir()
    (pasta / "ok.mp4").write_bytes(b"x")
    (tmp_path / "segredo.txt").write_text("nao")
    assert main._safe_child(pasta, "ok.mp4") is not None
    assert main._safe_child(pasta, "../segredo.txt") is None
    assert main._safe_child(pasta, "..") is None
    assert main._safe_child(pasta, "inexistente.mp4") is None


def test_rotas_de_arquivo_nao_vazam(client):
    for url in ("/api/youtube/file/..%2f..%2fproject.json", "/api/flow/gallery/..%5csegredo",
                "/api/motion/..%2fx.mp4", "/api/flow/reference/..%2fx"):
        assert client.get(url).status_code == 404


# ------------------------------------------------------------------ login
def test_login_com_senha_acentuada_nao_da_500(client, monkeypatch):
    # compare_digest com str não-ASCII levantava TypeError (HTTP 500).
    monkeypatch.setenv("APP_PASSWORD", "sênha-forte-ção-123")
    ok = client.post("/api/login", json={"password": "sênha-forte-ção-123"})
    assert ok.status_code == 200
    assert client.post("/api/login", json={"password": "errada-ç"}).status_code == 401


def test_cookie_de_sessao_libera_e_cookie_invalido_bloqueia(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "senha-forte-123")
    assert client.get("/api/catalog").status_code == 401
    assert client.post("/api/login", json={"password": "senha-forte-123"}).status_code == 200
    assert client.get("/api/catalog").status_code == 200
    client.cookies.clear()
    client.cookies.set("faceless_session", "cookie-invalido")
    assert client.get("/api/catalog").status_code == 401
    # valores não-ASCII não podem estourar (compare_digest com str levantava TypeError)
    assert main._safe_equals("çookie-inválido", "x") is False
    assert main._safe_equals("sênha", "sênha") is True


def test_login_tem_limite_de_tentativas(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "senha-forte-123")
    codes = [client.post("/api/login", json={"password": "x"}).status_code for _ in range(main.MAX_LOGIN_FAILS + 1)]
    assert codes[: main.MAX_LOGIN_FAILS] == [401] * main.MAX_LOGIN_FAILS
    assert codes[-1] == 429
    # mesmo a senha certa fica bloqueada durante a janela
    assert client.post("/api/login", json={"password": "senha-forte-123"}).status_code == 429


# ------------------------------------------------------------------ fila do Flow
def test_retry_da_fila_realmente_executa(client, monkeypatch):
    # Antes: BackgroundTasks() criado à mão nunca rodava; o item ficava em "processando" para sempre.
    gerado = Path(_TMP) / "img.png"
    gerado.write_bytes(b"png")

    def falso_generate_image(prompt, ratio, dest, **kw):
        out = main.flow.FLOW_GALLERY_DIR / "img_teste.png"
        out.write_bytes(b"png")
        return out

    monkeypatch.setattr(main.flow, "generate_image", falso_generate_image)
    item = {"id": "abc123", "status": "erro", "erro": "falhou", "prompt": "um gato astronauta", "kind": "image", "ratio": "16:9"}
    main._queue_save(item)
    r = client.post("/api/flow/queue/retry", json={"id": "abc123"})
    assert r.status_code == 200
    salvo = main.json.loads(main._queue_path("abc123").read_text(encoding="utf-8"))
    assert salvo["status"] == "concluido"
    assert salvo["filename"] == "img_teste.png"


# ------------------------------------------------------------------ narração: pausas entre blocos
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_merge_audio_insere_pausas(tmp_path):
    import narration_engine as ne

    ff = shutil.which("ffmpeg")
    partes = []
    for i in range(2):
        p = tmp_path / f"p{i}.mp3"
        subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=f=440:d=1", "-ar", "44100", "-ac", "1", str(p)],
                       capture_output=True, check=True)
        partes.append(p)
    saida = tmp_path / "out.mp3"
    duracao_reportada = ne.NarrationEngine()._merge_audio(partes, [1.0, 1.0], saida, ff)
    dur = float(subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(saida)], capture_output=True, text=True).stdout.strip())
    assert dur > 2.2  # 2 s de áudio + 0,3 s de pausa (antes a pausa nunca era criada: ~2,0 s)
    assert duracao_reportada == pytest.approx(dur, abs=0.15)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe não instalados")
def test_status_recupera_duracao_quando_job_antigo_tem_zero():
    job_id = "d" * 32
    audio = _salvar_narracao_completa_teste(job_id)
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i", "sine=f=440:d=1",
         "-ar", "44100", "-ac", "1", str(audio)],
        capture_output=True, check=True,
    )
    state = main.nar._read_job(job_id)
    state["duration"] = 0
    main.nar._write_job(job_id, state)

    status = main.nar.get_job(job_id)
    assert 0.8 <= status["duration"] <= 1.3
    assert main.nar._read_job(job_id)["duration"] == status["duration"]


def _salvar_narracao_completa_teste(job_id: str) -> Path:
    pasta = Path(_TMP) / "narrations" / job_id
    pasta.mkdir(parents=True, exist_ok=True)
    audio = pasta / "narration.mp3"
    audio.write_bytes(b"ID3-teste-audio")
    (pasta / "narration.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nTeste\n", encoding="utf-8"
    )
    main.nar._write_job(job_id, {
        "id": job_id, "status": "complete", "audio_file": "narration.mp3",
        "srt_file": "narration.srt", "paused": False, "cancelled": False,
    })
    return audio


def test_status_narracao_separa_url_de_player_e_download():
    job_id = "a" * 32
    _salvar_narracao_completa_teste(job_id)
    status = main.nar.get_job(job_id)
    assert status["audio_url"] == f"/api/narrations/{job_id}/audio"
    assert status["audio_download_url"] == f"/api/narrations/{job_id}/download"
    assert status["srt_url"] == f"/api/narrations/{job_id}/subtitles"


def test_player_recebe_mp3_com_disposition_inline(client):
    job_id = "b" * 32
    audio = _salvar_narracao_completa_teste(job_id)
    response = client.get(f"/api/narrations/{job_id}/audio")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == audio.read_bytes()


def test_download_narracao_continua_com_disposition_attachment(client):
    job_id = "c" * 32
    _salvar_narracao_completa_teste(job_id)
    response = client.get(f"/api/narrations/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")


# ------------------------------------------------------------------ fila de render, lote e recuperação
import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402


def _novo_projeto(status="ready", com_midia=True, **extra) -> str:
    pid = uuid.uuid4().hex
    (Path(_TMP) / pid).mkdir()
    state = {"id": pid, "title": f"proj {pid[:4]}", "status": status, "created_at": f"2026-01-01T00:00:{len(os.listdir(_TMP)):02d}",
             "scenes": [{"options": [{"url": "x"}]}] if com_midia else [{"options": []}], "stages": {}, "log": []}
    state.update(extra)
    main.write_state(pid, state)
    return pid


def _status(pid: str) -> str:
    return main.read_state(pid)["status"]


def _esperar(cond, timeout=8.0):
    fim = time.time() + timeout
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_recupera_projetos_interrompidos_no_reinicio():
    # Antes: o projeto ficava "rendering"/"searching" para sempre (ACTIVE_JOBS é só memória).
    busca = _novo_projeto("searching")
    montando = _novo_projeto("rendering", stages={"join": {"label": "j", "status": "running"}})
    capcut = _novo_projeto("complete", capcut={"status": "building"})
    pronto = _novo_projeto("ready")
    completo = _novo_projeto("complete")
    assert main.recover_interrupted_projects() >= 3
    assert _status(busca) == "ready" and _status(montando) == "ready"
    assert main.read_state(montando)["stages"]["join"]["status"] == "pending"
    assert main.read_state(capcut)["capcut"] == {"status": "none"} and _status(capcut) == "complete"
    assert _status(pronto) == "ready" and _status(completo) == "complete"


def test_fila_monta_um_projeto_por_vez_e_em_ordem(client, monkeypatch):
    ativos, pico, ordem = [0], [0], []
    lock = threading.Lock()

    def render_falso(pid):
        with lock:
            ativos[0] += 1
            pico[0] = max(pico[0], ativos[0])
            ordem.append(pid)
        time.sleep(0.05)
        main.patch_state(pid, lambda s: s.update({"status": "complete"}))
        with lock:
            ativos[0] -= 1

    monkeypatch.setattr(main, "render_project", render_falso)
    ids = [_novo_projeto() for _ in range(3)]
    for pid in ids:
        r = client.post(f"/api/projects/{pid}/render")
        assert r.status_code == 200 and r.json()["status"] == "queued_render"
    assert _esperar(lambda: all(_status(p) == "complete" for p in ids))
    assert pico[0] == 1          # nunca dois renders ao mesmo tempo
    assert ordem == ids          # primeiro a entrar, primeiro a montar


def test_cancelar_projeto_que_espera_na_fila(client, monkeypatch):
    liberar, chamados = threading.Event(), []

    def render_falso(pid):
        chamados.append(pid)
        liberar.wait(5)
        main.patch_state(pid, lambda s: s.update({"status": "complete"}))

    monkeypatch.setattr(main, "render_project", render_falso)
    primeiro, segundo = _novo_projeto(), _novo_projeto()
    client.post(f"/api/projects/{primeiro}/render")
    assert _esperar(lambda: primeiro in chamados)
    client.post(f"/api/projects/{segundo}/render")
    assert client.get("/api/render-queue").json()["waiting"][0]["id"] == segundo
    assert client.post(f"/api/projects/{segundo}/cancel").status_code == 200
    liberar.set()
    assert _esperar(lambda: _status(segundo) == "ready" and _status(primeiro) == "complete")
    assert chamados == [primeiro]  # o cancelado nunca chegou a renderizar


def test_render_em_lote_enfileira_prontos_e_explica_os_ignorados(client, monkeypatch):
    monkeypatch.setattr(main, "render_project", lambda pid: main.patch_state(pid, lambda s: s.update({"status": "complete"})))
    for p in Path(_TMP).iterdir():  # isola de projetos de outros testes
        shutil.rmtree(p, ignore_errors=True)
    a, b = _novo_projeto(), _novo_projeto()
    sem_midia = _novo_projeto(com_midia=False)
    r = client.post("/api/projects/render-batch").json()
    assert [q["id"] for q in r["queued"]] == [a, b]
    assert [s["id"] for s in r["skipped"]] == [sem_midia]
    assert _esperar(lambda: _status(a) == "complete" and _status(b) == "complete")
    # ids explícitos: um projeto já montado é aceito de novo? não, só "ready" entra; aqui forçamos um inexistente
    r2 = client.post("/api/projects/render-batch", json={"ids": [sem_midia]}).json()
    assert r2["queued"] == [] and len(r2["skipped"]) == 1


# ------------------------------------------------------------------ OpenRouter, proporção de mídia, Storyblocks e limite de B-roll
def test_normalize_settings_limita_percentual_e_duracao_de_clipes():
    cfg = main.normalize_settings({
        "video_percent": 145,
        "max_video_seconds": 40,
        "openrouter_model": "google/gemini-2.5-flash",
    })
    assert cfg["video_percent"] == 100
    assert cfg["max_video_seconds"] == 10
    assert cfg["openrouter_model"] == "google/gemini-2.5-flash"
    assert cfg["max_search_requests"] == 24

    cfg = main.normalize_settings({"video_percent": -5, "max_video_seconds": 0, "max_search_requests": 0})
    assert cfg["video_percent"] == 0
    assert cfg["max_video_seconds"] == 1
    assert cfg["max_search_requests"] == 1


def test_auto_pick_respeita_cota_video_e_prioriza_nota_de_movimento():
    from scenes import auto_pick

    cenas = []
    for idx, score in enumerate((95, 75, 35, 10)):
        cenas.append({
            "id": f"scene-{idx}",
            "start": 0,
            "end": 5,
            "motion_score": score,
            "recommended_media": "video" if score >= 50 else "image",
            "options": [
                {"id": f"vid-{idx}", "provider": "Pexels", "media_type": "video", "duration": 10, "width": 1280, "height": 720},
                {"id": f"img-{idx}", "provider": "Unsplash", "media_type": "image", "width": 1280, "height": 720},
            ],
        })

    auto_pick(cenas, "mixed", "16:9", video_percent=50)
    escolhidos = [c["options"][c["selected"]]["media_type"] for c in cenas]
    assert escolhidos == ["video", "video", "image", "image"]
    assert [c["target_media_type"] for c in cenas] == escolhidos


def test_openrouter_gera_consultas_com_contexto_e_nota_de_movimento(monkeypatch):
    import json as _json

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": _json.dumps({
                "palavras_chave": ["carro", "estrada"],
                "consultas": ["car driving on highway", "traffic aerial view"],
                "descricao_visual": "Carros em movimento numa rodovia.",
                "motion_score": 92,
                "recommended_media": "video",
            })}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr(scene_planner.requests, "post", fake_post)
    plan = scene_planner.gerar_consultas_para_cena(
        "O carro acelera pela estrada.",
        idioma="pt",
        contexto="O documentário explica como o trânsito muda a vida nas grandes cidades.",
        model="google/gemini-2.5-flash",
    )
    assert plan["provider"] == "openrouter"
    assert plan["motion_score"] == 92
    assert plan["recommended_media"] == "video"
    assert "contexto" in captured["body"]["messages"][1]["content"].lower()
    assert captured["body"]["model"] == "google/gemini-2.5-flash"


def test_storyblocks_assinatura_hmac_tem_formato_valido():
    import hashlib as _hashlib
    import hmac as _hmac
    import storyblocks_mgr

    resource = "/api/v2/videos/search"
    params = storyblocks_mgr._signed_params(resource, "api-key", "api-secret")
    expected = _hmac.new(
        ("api-secret" + params["EXPIRES"]).encode("utf-8"),
        resource.encode("utf-8"),
        _hashlib.sha256,
    ).hexdigest()
    assert params["APIKEY"] == "api-key"
    assert params["HMAC"] == expected
    assert params["EXPIRES"].isdigit()


def test_youtube_thumbnail_source_cria_imagem_com_aviso(monkeypatch):
    import providers

    monkeypatch.setattr(providers.youtube_mgr, "youtube_search", lambda *args, **kwargs: [{
        "id": "yt_abcdefghijk",
        "provider": "YouTube",
        "media_type": "video",
        "download_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
        "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "title": "City traffic footage",
        "duration": 30,
    }])
    options, messages = providers.search_scene_assets(
        "city traffic", ["youtube_frame"], {}, per=1, orientation="landscape",
    )
    assert options
    assert options[0]["media_type"] == "image"
    assert options[0]["provider"] == "YouTube · quadro"
    assert options[0]["requires_permission"] is True
    assert options[0]["frame_from_video"] is True
    assert options[0]["download_url"].startswith("https://www.youtube.com/watch")


def test_limit_video_duration_reencoda_clipe_acima_da_cota(monkeypatch, tmp_path):
    import render

    source = tmp_path / "video-original.mp4"
    source.write_bytes(b"origem")
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("fake")
    monkeypatch.setattr(render, "ffmpeg_path", lambda: str(fake_ffmpeg))
    monkeypatch.setattr(render, "media_duration", lambda path: 14.0 if Path(path).name == source.name else 9.9)

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"x" * 2048)
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    result = render._limit_video_duration(source, tmp_path, max_seconds=10)
    assert result.exists()
    assert result != source
    assert "10s.mp4" in result.name
    assert render.media_duration(result) <= 10


def test_storyblocks_route_exige_as_duas_credenciais(client, monkeypatch):
    monkeypatch.setenv("STORYBLOCKS_API_KEY", "")
    monkeypatch.setenv("STORYBLOCKS_API_SECRET", "")
    response = client.post("/api/storyblocks/search", json={"query": "nature"})
    assert response.status_code == 400
    assert "API Key" in response.json()["detail"]


def test_openrouter_modelos_exige_chave(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    response = client.get("/api/openrouter/models")
    assert response.status_code == 400
    assert "OPENROUTER_API_KEY" in response.json()["detail"]

def test_diagnostico_api_nao_expoe_chaves(client, monkeypatch):
    import doctor

    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-super-secreta-de-teste")
    response = client.get("/api/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert "checks" in payload and "counts" in payload
    assert isinstance(payload["checks"], list)
    assert "chave-super-secreta-de-teste" not in response.text
    assert all("detail" in item and "status" in item for item in payload["checks"])



def test_openrouter_confere_previews_e_descarta_midia_sem_relacao(monkeypatch):
    import json as _json
    import media_relevance

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": _json.dumps({
                "resultados": [
                    {"indice": 0, "nota": 94, "motivo": "Mostra exatamente a ação narrada."},
                    {"indice": 1, "nota": 18, "motivo": "A prévia mostra um assunto diferente."},
                ]
            })}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr(media_relevance.requests, "post", fake_post)
    candidates = [
        {"id": "good", "provider": "Pexels", "media_type": "video", "thumbnail": "https://img.test/good.jpg", "title": "Used car purchase"},
        {"id": "bad", "provider": "YouTube", "media_type": "video", "thumbnail": "https://img.test/bad.jpg", "title": "Luxury sports car"},
    ]
    accepted, report = media_relevance.verify_scene_candidates(
        scene_text="Ele comprou um carro usado à vista.",
        visual_description="Pessoa comprando um carro usado em uma loja simples.",
        context="A narração compara comprar à vista com financiar um carro.",
        candidates=candidates,
        model="google/gemini-2.5-flash",
        min_score=68,
    )

    assert report["status"] == "verified"
    assert report["accepted"] == 1
    assert report["rejected"] == 1
    assert len(accepted) == 1
    assert accepted[0]["id"] == "good"
    assert accepted[0]["media_match_score"] == 94
    assert accepted[0]["relevance_verified"] is True
    assert any(part.get("type") == "image_url" for part in captured["body"]["messages"][1]["content"])


def test_openrouter_visual_sem_chave_nao_quebra_busca(monkeypatch):
    import media_relevance

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    candidates = [{"id": "a", "thumbnail": "https://img.test/a.jpg"}]
    kept, report = media_relevance.verify_scene_candidates(
        scene_text="Uma fala de teste.",
        visual_description="Cena ilustrativa.",
        context="",
        candidates=candidates,
    )
    assert kept == candidates
    assert report["status"] == "unavailable"
    assert report["accepted"] == 1


def test_limite_global_de_consultas_por_cena(monkeypatch):
    import providers

    chamadas = []

    def fake_search(query, api_key, media_type, per, orientation):
        chamadas.append((query, media_type))
        return []

    monkeypatch.setattr(providers, "provider_key", lambda *args: "key")
    monkeypatch.setattr(providers, "pexels_search", fake_search)
    usage = {}
    options, messages = providers.search_scene_assets(
        "consulta principal",
        ["pexels_video", "pexels_image"],
        {},
        per=2,
        queries=["consulta dois", "consulta três"],
        max_requests=3,
        usage=usage,
    )

    assert chamadas == [
        ("consulta principal", "video"),
        ("consulta principal", "image"),
        ("consulta dois", "video"),
    ]
    assert options == []
    assert usage["requests"] == 3
    assert usage["limit"] == 3
    assert usage["remaining"] == 0
    assert usage["limit_reached"] is True
    assert usage["requests_by_source"] == {"pexels_video": 2, "pexels_image": 1}


def test_limite_de_consultas_nao_ultrapassa_teto_absoluto(monkeypatch):
    import providers

    chamadas = []
    monkeypatch.setattr(providers, "provider_key", lambda *args: "key")
    monkeypatch.setattr(
        providers, "pexels_search",
        lambda query, api_key, media_type, per, orientation: chamadas.append(query) or [],
    )
    usage = {}
    providers.search_scene_assets(
        "principal",
        ["pexels_video"],
        {},
        queries=[f"consulta {n}" for n in range(2, 20)],
        max_requests=999,
        usage=usage,
    )
    assert usage["limit"] == 24
    assert usage["requests"] <= 24
