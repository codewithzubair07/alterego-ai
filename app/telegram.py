"""Telegram Bot API client and message formatting utilities."""

from typing import Any
import httpx

from app.config import Settings, get_settings
from app.logger import logger

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_message(text: str, max_chars: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long text message into chunks of at most max_chars without breaking mid-word when possible."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Look for the last double newline within max_chars
        split_idx = remaining.rfind("\n\n", 0, max_chars)
        if split_idx == -1:
            # Fall back to single newline
            split_idx = remaining.rfind("\n", 0, max_chars)
        if split_idx == -1:
            # Fall back to whitespace
            split_idx = remaining.rfind(" ", 0, max_chars)
        if split_idx <= 0:
            # If no convenient break found, hard-slice at max_chars
            split_idx = max_chars

        chunk = remaining[:split_idx].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_idx:].lstrip()

    return chunks


class TelegramError(Exception):
    """Base exception for Telegram API interactions."""


class TelegramClient:
    """Async client for Telegram Bot API operations."""

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or get_settings()
        self._external_client = client

    @property
    def bot_token(self) -> str:
        return self.config.telegram_bot_token.get_secret_value()

    @property
    def base_url(self) -> str:
        token = self.bot_token
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not configured.")
        return f"{self.config.telegram_api_base.rstrip('/')}/bot{token}"

    def _sanitize(self, text: str) -> str:
        token = self.bot_token
        if token and len(token) > 4:
            text = text.replace(token, "[REDACTED_TELEGRAM_TOKEN]")
        return text

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute an HTTP request to Telegram Bot API."""
        url = f"{self.base_url}/{endpoint}"
        async def _call(cli: httpx.AsyncClient) -> dict[str, Any]:
            try:
                response = await cli.post(url, json=payload or {}, timeout=timeout)
                data = response.json()
                if not data.get("ok"):
                    desc = self._sanitize(str(data.get("description", "Unknown Telegram error")))
                    raise TelegramError(f"Telegram API error ({data.get('error_code')}): {desc}")
                return data
            except httpx.HTTPError as err:
                raise TelegramError(self._sanitize(f"HTTP error communicating with Telegram: {err}")) from err

        if self._external_client is not None:
            return await _call(self._external_client)
        async with httpx.AsyncClient() as cli:
            return await _call(cli)

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> bool:
        """Send a chat action indicator (e.g. typing) to the chat."""
        try:
            res = await self._request("POST", "sendChatAction", {"chat_id": chat_id, "action": action}, timeout=10.0)
            return bool(res.get("ok"))
        except Exception as err:
            logger.debug("Failed to send chat action: %s", self._sanitize(str(err)))
            return False

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
    ) -> list[dict[str, Any]]:
        """Send a message to a chat, splitting into chunks if text exceeds limit."""
        chunks = split_message(text)
        results: list[dict[str, Any]] = []
        for chunk in chunks:
            res = await self._request("POST", "sendMessage", {"chat_id": chat_id, "text": chunk})
            results.append(res)
        return results

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 30,
    ) -> list[dict[str, Any]]:
        """Long poll updates from Telegram (used in local development)."""
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        # HTTP timeout must be slightly longer than Telegram long-poll timeout
        res = await self._request("POST", "getUpdates", payload=payload, timeout=float(timeout + 10))
        return res.get("result", [])

