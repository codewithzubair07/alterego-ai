"""Tests for application settings and secret protection."""

from pathlib import Path
from pydantic import SecretStr

from app.config import Settings


def test_settings_default_values():
    settings = Settings()
    assert settings.persona_name == "Juber"
    assert settings.llm_provider == "groq"
    assert "groq.com" in settings.llm_base_url
    assert settings.llm_model == "llama-3.3-70b-versatile"
    assert settings.chat_completions_url == "https://api.groq.com/openai/v1/chat/completions"


def test_secret_key_not_exposed_in_repr_or_str():
    raw_key = "gsk_super_secret_key_to_never_leak_987654321"
    settings = Settings(llm_api_key=SecretStr(raw_key))

    # str() and repr() must hide the secret
    assert raw_key not in str(settings.llm_api_key)
    assert raw_key not in repr(settings.llm_api_key)
    assert raw_key not in repr(settings)

    # get_secret_value() extracts it cleanly when needed for auth
    assert settings.llm_api_key.get_secret_value() == raw_key


def test_chat_completions_url_normalization():
    # URL without trailing slash
    s1 = Settings(llm_base_url="https://api.groq.com/openai/v1")
    assert s1.chat_completions_url == "https://api.groq.com/openai/v1/chat/completions"

    # URL with trailing slash
    s2 = Settings(llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    assert s2.chat_completions_url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    # URL that already includes /chat/completions
    s3 = Settings(llm_base_url="https://custom.endpoint.com/v1/chat/completions")
    assert s3.chat_completions_url == "https://custom.endpoint.com/v1/chat/completions"

