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
    ne.NarrationEngine()._merge_audio(partes, [1.0, 1.0], saida, ff)
    dur = float(subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(saida)], capture_output=True, text=True).stdout.strip())
    assert dur > 2.2  # 2 s de áudio + 0,3 s de pausa (antes a pausa nunca era criada: ~2,0 s)


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
