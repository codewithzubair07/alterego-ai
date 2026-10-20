"""OpenAI-compatible LLM client wrapper using HTTPX."""

import asyncio
from typing import Any, Mapping

import httpx

from app.config import Settings, get_settings
from app.logger import logger


class LLMError(Exception):
    """Base exception for LLM interaction failures."""


class LLMAuthenticationError(LLMError):
    """Raised when the provider rejects the API key."""


class LLMRateLimitError(LLMError):
    """Raised when the provider rate limits requests and retries are exhausted."""


class LLMResponseError(LLMError):
    """Raised when provider returns an unparseable or error payload."""


def _sanitize_error_text(text: str, secret_key: str) -> str:
    """Ensure secret key never leaks in exception messages."""
    if secret_key and len(secret_key) > 4:
        text = text.replace(secret_key, "[REDACTED_API_KEY]")
    return text


async def llm(
    messages: list[dict[str, str]],
    config: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> str:
    """The single entry point for invoking LLM chat completion.

    Connects to any OpenAI-compatible chat completions endpoint (Groq, Gemini,
    OpenRouter, Ollama, OpenAI) using configuration from settings.

    Args:
        messages: List of chat messages, e.g. [{"role": "system", "content": "..."}, ...]
        config: Application settings. Defaults to singleton settings.
        client: Optional httpx.AsyncClient (useful for connection pooling or testing).

    Returns:
        The content string returned by the model.

    Raises:
        LLMAuthenticationError: When credentials are invalid (HTTP 401/403).
        LLMRateLimitError: When provider rate limits after retries (HTTP 429).
        LLMResponseError: When response payload is invalid or non-2xx status.
    """
    settings = config or get_settings()
    api_key = settings.llm_api_key.get_secret_value()
    target_url = settings.chat_completions_url

    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }

    max_retries = max(0, settings.llm_max_retries)
    timeout = settings.llm_timeout_seconds

    # Helper for making the actual call with retries
    async def _execute_request(http_client: httpx.AsyncClient) -> str:
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                logger.debug(
                    "Calling LLM provider=%s model=%s (attempt %d/%d)",
                    settings.llm_provider,
                    settings.llm_model,
                    attempt + 1,
                    max_retries + 1,
                )
                response = await http_client.post(
                    target_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )

                # Check HTTP status
                if response.status_code == 200:
                    try:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        if content is None:
                            return ""
                        return str(content).strip()
                    except (KeyError, IndexError, TypeError, ValueError) as err:
                        raise LLMResponseError(
                            f"Invalid response structure from {settings.llm_provider}: {err}"
                        ) from err

                # Handle authentication errors immediately (do not retry)
                if response.status_code in (401, 403):
                    raise LLMAuthenticationError(
                        f"Authentication failed for provider '{settings.llm_provider}' (HTTP {response.status_code}). "
                        f"Check your API key in .env."
                    )

                # Handle rate limiting (429) and server errors (5xx) with backoff
                if response.status_code == 429 or response.status_code >= 500:
                    raw_text = _sanitize_error_text(response.text, api_key)
                    if attempt < max_retries:
                        backoff = (2**attempt) * 0.5
                        logger.warning(
                            "Transient LLM HTTP %d error from %s. Retrying in %.1fs...",
                            response.status_code,
                            settings.llm_provider,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                    if response.status_code == 429:
                        raise LLMRateLimitError(
                            f"Rate limit exceeded from provider '{settings.llm_provider}' after {max_retries + 1} attempts: {raw_text}"
                        )
                    raise LLMResponseError(
                        f"Server error from provider '{settings.llm_provider}' (HTTP {response.status_code}): {raw_text}"
                    )

                # Any other 4xx client errors (do not retry)
                raw_text = _sanitize_error_text(response.text, api_key)
                raise LLMResponseError(
                    f"Client error from provider '{settings.llm_provider}' (HTTP {response.status_code}): {raw_text}"
                )

            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                last_exception = net_err
                if attempt < max_retries:
                    backoff = (2**attempt) * 0.5
                    logger.warning(
                        "Network/Timeout error calling %s. Retrying in %.1fs...",
                        settings.llm_provider,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

                raise LLMResponseError(
                    f"Network or timeout error contacting {settings.llm_provider} after {max_retries + 1} attempts: {net_err}"
                ) from net_err

        # Fallback if loop ended unexpectedly
        raise LLMResponseError(
            f"Failed to communicate with LLM provider: {last_exception}"
        )

    if client is not None:
        return await _execute_request(client)

    async with httpx.AsyncClient() as new_client:
        return await _execute_request(new_client)

