"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Persona settings
    persona_name: str = Field(
        default="Juber",
        description="Name of the person being modeled by the AI alter ego",
    )
    persona_dir: Path = Field(
        default=Path("persona"),
        description="Directory containing style_guide.md, examples.md, facts.md, rules.md",
    )

    # LLM Settings (OpenAI-compatible)
    llm_provider: str = Field(
        default="groq",
        description="Active provider identifier (groq, gemini, openrouter, etc.)",
    )
    llm_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Base URL for OpenAI-compatible chat completions endpoint",
    )
    llm_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Exact model identifier passed to the chat completion API",
    )
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key for the active LLM provider. Kept secret and never serialized.",
    )
    llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the LLM",
    )
    llm_max_tokens: int = Field(
        default=600,
        gt=0,
        description="Maximum tokens to generate in a completion",
    )
    llm_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP request timeout in seconds",
    )
    llm_max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts on transient network or 429/5xx errors",
    )

    # App Environment
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    @property
    def chat_completions_url(self) -> str:
        """Returns normalized full URL for the chat completions endpoint."""
        base = self.llm_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()

