"""Logging configuration with secret redaction."""

import logging
import re
from typing import Any

from app.config import get_settings

# Regex patterns matching common API keys and auth headers
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{8,}", re.IGNORECASE),
    re.compile(r"gsk_[A-Za-z0-9_]{16,}", re.IGNORECASE),
    re.compile(r"AIzaSy[A-Za-z0-9\-_]{25,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"[0-9]{8,11}:[a-zA-Z0-9_-]{34,36}"),  # Telegram bot tokens
]


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts API keys and sensitive tokens from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self.redact(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.redact(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True

    @staticmethod
    def redact(text: str) -> str:
        """Replace detected secrets with sanitized placeholders."""
        try:
            settings = get_settings()
            current_key = settings.llm_api_key.get_secret_value()
            if current_key and len(current_key) > 4:
                text = text.replace(current_key, "[REDACTED_API_KEY]")
            for secret_obj in (
                settings.telegram_bot_token,
                settings.telegram_webhook_secret,
            ):
                val = secret_obj.get_secret_value()
                if val and len(val) > 4:
                    text = text.replace(val, "[REDACTED_SECRET]")
        except Exception:
            pass

        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[REDACTED_SECRET]", text)
        return text


def setup_logger(name: str = "alterego") -> logging.Logger:
    """Set up and return a logger with redaction filter installed."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretRedactingFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = setup_logger()

