"""Pytest configuration and fixtures."""

from pathlib import Path
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.persona import PersonaLoader


@pytest.fixture
def mock_settings() -> Settings:
    """Fixture providing clean test settings with dummy credentials."""
    return Settings(
        persona_name="TestCreator",
        persona_dir=Path("persona"),
        llm_provider="groq",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_model="llama-3.3-70b-versatile",
        llm_api_key=SecretStr("gsk_secret_test_key_1234567890abcdef"),
        llm_temperature=0.7,
        llm_max_tokens=256,
        llm_timeout_seconds=5.0,
        llm_max_retries=2,
        telegram_bot_token=SecretStr("123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_mock"),
        telegram_webhook_secret=SecretStr("mock_webhook_secret_98765"),
    )


@pytest.fixture
def persona_loader(tmp_path: Path) -> PersonaLoader:
    """Fixture providing a PersonaLoader pointing to a valid temporary persona directory."""
    pdir = tmp_path / "persona"
    pdir.mkdir()
    (pdir / "style_guide.md").write_text("# Style\nConcise and direct.", encoding="utf-8")
    (pdir / "examples.md").write_text("# Examples\nGood reply.", encoding="utf-8")
    (pdir / "facts.md").write_text(
        "## Projects\nBuilt Alterego.\n\n## Skills\nPython, FastAPI.",
        encoding="utf-8",
    )
    (pdir / "rules.md").write_text("# Rules\nNever share secrets.", encoding="utf-8")
    return PersonaLoader(persona_dir=pdir)

