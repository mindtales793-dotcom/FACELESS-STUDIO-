"""Sistema de Skills de Roteiros para o Faceless Cloud Studio.

Carrega as skills da pasta Biblioteca/01 - Roteiros e as expõe
como opções de geração de roteiro no editor de vídeo.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests

SKILLS_ROOT = Path(
    os.getenv(
        "SKILLS_ROOT",
        r"C:\Users\Lucas\Downloads\WebDark-Skills-Alunos-2026-11-03\Biblioteca\01 - Roteiros",
    )
)

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
SKILL_TEXT_MODEL = os.getenv("SKILL_TEXT_MODEL", "gemini-2.5-flash")


def _gemini_text(prompt: str) -> str:
    """Gera texto com a Gemini API. Devolve '' quando não há chave ou em caso de erro."""
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        return ""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
    }
    try:
        resp = requests.post(
            f"{GEMINI_API}/{SKILL_TEXT_MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=(20, 120),
        )
        if not resp.ok:
            return ""
        data = resp.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        for part in parts:
            if part.get("text"):
                return str(part["text"]).strip()
    except Exception:
        return ""
    return ""


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extrai name e description do cabeçalho --- ... --- de um SKILL.md."""
    data: dict[str, str] = {}
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m:
        block = m.group(1)
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
    return data


def load_skills() -> list[dict[str, Any]]:
    """Lê todos os SKILL.md da pasta de roteiros (busca recursiva) e retorna lista de skills."""
    skills: list[dict[str, Any]] = []
    if not SKILLS_ROOT.exists():
        return skills

    for skill_md in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        skill_dir = skill_md.parent

        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        meta = _parse_frontmatter(text)
        skill_id = meta.get("name") or skill_dir.name
        description = meta.get("description") or ""

        # Lê o método principal se existir
        method_file = skill_dir / "method.md"
        method_text = ""
        if method_file.exists():
            try:
                method_text = method_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        # Lê o roteiro principal se existir (para uso como exemplo/template)
        script_file = None
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for f in scripts_dir.iterdir():
                if f.suffix.lower() in (".txt", ".md"):
                    script_file = f.name
                    break

        skills.append(
            {
                "id": skill_id,
                "name": skill_id.replace("_", " ").title(),
                "description": description,
                "category": skill_dir.parent.name,
                "folder": skill_dir.name,
                "path": str(skill_dir),
                "has_method": bool(method_text.strip()),
                "method_preview": method_text[:300] if method_text else "",
                "script_template": script_file,
                "full_text": text,
            }
        )

    return skills


def get_skill(skill_id: str) -> dict[str, Any] | None:
    """Retorna os detalhes de uma skill específica pelo id."""
    for s in load_skills():
        if s["id"] == skill_id:
            return s
    return None


def generate_narration_from_skill(
    skill_id: str,
    topic: str,
    language: str = "pt-BR",
    char_count: int | None = None,
) -> dict[str, Any]:
    """Gera um roteiro usando a skill selecionada.

    Esta função é um wrapper que prepara os dados para a geração.
    A geração real de texto pode ser feita pelo modelo de IA integrado
    ou por um passo posterior no pipeline.
    """
    skill = get_skill(skill_id)
    if not skill:
        return {"error": f"Skill '{skill_id}' não encontrada."}

    instrucao = (
        "Você é um roteirista profissional de vídeos faceless (sem rosto). "
        "Siga EXATAMENTE o método da skill abaixo para escrever a narração.\n\n"
        f"## MÉTODO DA SKILL: {skill['name']}\n"
        f"{(skill.get('full_text') or '')[:14000]}\n\n"
        "## TAREFA\n"
        f"Tópico do vídeo: {topic}\n"
        f"Idioma: {language}\n"
        + (f"Tamanho alvo: aproximadamente {char_count} caracteres.\n" if char_count else "")
        + "Escreva APENAS a narração final, pronta para gravação: sem títulos, sem markdown, "
          "sem comentários e sem instruções de cena."
    )
    texto = _gemini_text(instrucao)

    if texto:
        return {
            "skill_id": skill_id,
            "skill_name": skill["name"],
            "description": skill["description"],
            "topic": topic,
            "language": language,
            "char_count": len(texto),
            "method": skill.get("method_preview", ""),
            "full_method": skill.get("full_text", ""),
            "status": "ready",
            "generated": True,
            "message": texto,
        }

    return {
        "skill_id": skill_id,
        "skill_name": skill["name"],
        "description": skill["description"],
        "topic": topic,
        "language": language,
        "char_count": char_count,
        "method": skill.get("method_preview", ""),
        "full_method": skill.get("full_text", ""),
        "status": "ready",
        "generated": False,
        "message": (
            f"Skill '{skill['name']}' carregada. "
            f"Tópico: {topic}. Idioma: {language}."
            + (f" Caracteres alvo: {char_count}." if char_count else "")
            + " Configure a GEMINI_API_KEY para gerar o roteiro automaticamente."
        ),
    }
