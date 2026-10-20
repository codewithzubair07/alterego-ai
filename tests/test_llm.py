"""Tests for the provider-agnostic llm() wrapper."""

from pydantic import SecretStr
import pytest
import respx
import httpx

from app.config import Settings
from app.llm import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMResponseError,
    llm,
)


@pytest.mark.asyncio
@respx.mock
async def test_llm_successful_completion(mock_settings: Settings):
    secret_key = mock_settings.llm_api_key.get_secret_value()
    mock_route = respx.post(mock_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hey there! I am the AI version of Juber.",
                        }
                    }
                ]
            },
        )
    )

    messages = [{"role": "user", "content": "Hello!"}]
    reply = await llm(messages=messages, config=mock_settings)

    assert reply == "Hey there! I am the AI version of Juber."
    assert mock_route.called
    req = mock_route.calls.last.request
    assert req.headers["Authorization"] == f"Bearer {secret_key}"
    payload = req.read().decode("utf-8")
    assert mock_settings.llm_model in payload
    assert "Hello!" in payload


@pytest.mark.asyncio
@respx.mock
async def test_llm_swappable_gemini_provider():
    gemini_settings = Settings(
        persona_name="Juber",
        llm_provider="gemini",
        llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        llm_model="gemini-2.0-flash",
        llm_api_key=SecretStr("AIzaSy_fake_test_gemini_key_12345"),
        llm_max_retries=1,
    )

    mock_route = respx.post(gemini_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Gemini response via OpenAI-compatible route.",
                        }
                    }
                ]
            },
        )
    )

    messages = [{"role": "user", "content": "Testing provider swap"}]
    reply = await llm(messages=messages, config=gemini_settings)

    assert reply == "Gemini response via OpenAI-compatible route."
    assert mock_route.called
    req = mock_route.calls.last.request
    assert "generativelanguage.googleapis.com" in str(req.url)
    assert req.headers["Authorization"] == f"Bearer {gemini_settings.llm_api_key.get_secret_value()}"


@pytest.mark.asyncio
@respx.mock
async def test_llm_auth_failure_does_not_leak_key(mock_settings: Settings):
    secret_key = mock_settings.llm_api_key.get_secret_value()
    respx.post(mock_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            401,
            json={"error": {"message": f"Invalid API key: {secret_key}"}},
        )
    )

    messages = [{"role": "user", "content": "Hi"}]
    with pytest.raises(LLMAuthenticationError) as exc_info:
        await llm(messages=messages, config=mock_settings)

    # The exception message must never contain the raw secret key
    assert secret_key not in str(exc_info.value)
    assert "Authentication failed" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_llm_rate_limit_retries_and_exhaustion(mock_settings: Settings):
    # Set max_retries = 1 for faster test execution
    quick_settings = mock_settings.model_copy(update={"llm_max_retries": 1})
    secret_key = quick_settings.llm_api_key.get_secret_value()

    mock_route = respx.post(quick_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            429,
            json={"error": {"message": f"Rate limit reached for {secret_key}"}},
        )
    )

    messages = [{"role": "user", "content": "Ping"}]
    with pytest.raises(LLMRateLimitError) as exc_info:
        await llm(messages=messages, config=quick_settings)

    # Initial call + 1 retry = 2 total calls
    assert mock_route.call_count == 2
    assert secret_key not in str(exc_info.value)
    assert "[REDACTED_API_KEY]" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_llm_transient_error_recovers_on_retry(mock_settings: Settings):
    quick_settings = mock_settings.model_copy(update={"llm_max_retries": 2})

    # First attempt: 503 Service Unavailable, Second attempt: 200 OK
    respx.post(quick_settings.chat_completions_url).mock(
        side_effect=[
            httpx.Response(503, text="Service temporarily overloaded"),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Recovered from glitch!",
                            }
                        }
                    ]
                },
            ),
        ]
    )

    messages = [{"role": "user", "content": "Hello"}]
    reply = await llm(messages=messages, config=quick_settings)
    assert reply == "Recovered from glitch!"


@pytest.mark.asyncio
@respx.mock
async def test_llm_malformed_response_raises_response_error(mock_settings: Settings):
    respx.post(mock_settings.chat_completions_url).mock(
        return_value=httpx.Response(200, json={"unexpected": "structure"})
    )

    messages = [{"role": "user", "content": "Hello"}]
    with pytest.raises(LLMResponseError) as exc_info:
        await llm(messages=messages, config=mock_settings)

    assert "Invalid response structure" in str(exc_info.value)

