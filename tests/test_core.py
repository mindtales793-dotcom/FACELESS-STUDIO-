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
