"""Tests for persona file loading, parsing, and prompt assembly."""

from pathlib import Path
import pytest

from app.persona import PersonaFileNotFoundError, PersonaLoader


def test_persona_loader_loads_existing_workspace_files():
    loader = PersonaLoader(persona_dir=Path("persona"))
    data = loader.load()

    assert data.style_guide
    assert data.examples
    assert data.facts
    assert data.rules
    assert "[TODO:" in data.style_guide
    assert "[TODO:" in data.facts


def test_persona_loader_missing_directory_raises(tmp_path: Path):
    loader = PersonaLoader(persona_dir=tmp_path / "non_existent_dir")
    with pytest.raises(PersonaFileNotFoundError):
        loader.load()


def test_persona_loader_missing_file_raises(tmp_path: Path):
    pdir = tmp_path / "incomplete_persona"
    pdir.mkdir()
    (pdir / "style_guide.md").write_text("# Style", encoding="utf-8")
    (pdir / "examples.md").write_text("# Examples", encoding="utf-8")
    # Missing facts.md and rules.md
    loader = PersonaLoader(persona_dir=pdir)
    with pytest.raises(PersonaFileNotFoundError) as exc_info:
        loader.load()
    assert "facts.md" in str(exc_info.value)


def test_get_fact_sections_parses_sections(persona_loader: PersonaLoader):
    sections = persona_loader.get_fact_sections()
    assert len(sections) == 2

    titles = [s.title for s in sections]
    assert "Projects" in titles
    assert "Skills" in titles

    skills_sec = next(s for s in sections if s.title == "Skills")
    assert "FastAPI" in skills_sec.content
    assert "python" in skills_sec.tags
    assert "fastapi" in skills_sec.tags


def test_build_system_prompt_includes_persona_name_and_fallback(persona_loader: PersonaLoader):
    prompt = persona_loader.build_system_prompt(persona_name="Juber")

    assert "AI alter ego of Juber" in prompt
    assert "CORE RULES & BOUNDARIES" in prompt
    assert "STYLE GUIDE" in prompt
    assert "suggest asking the real Juber" in prompt


def test_build_system_prompt_with_retrieved_facts(persona_loader: PersonaLoader):
    retrieved = [
        "## Projects\nBuilt Alterego open source AI clone.",
        "## Tech Stack\nPython 3.12, FastAPI.",
    ]
    prompt = persona_loader.build_system_prompt(
        persona_name="NexusCreator",
        retrieved_facts=retrieved,
    )

    assert "AI alter ego of NexusCreator" in prompt
    assert "Relevant Facts about NexusCreator:" in prompt
    assert "Built Alterego open source AI clone" in prompt

