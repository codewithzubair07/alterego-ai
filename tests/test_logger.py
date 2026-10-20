"""Tests for logger secret redaction."""

import logging
from pydantic import SecretStr

from app.config import Settings
from app.logger import SecretRedactingFilter


def test_logger_redacts_api_key_and_patterns(monkeypatch):
    test_key = "gsk_test_api_key_very_secret_9999"
    # Monkeypatch get_settings in app.logger
    monkeypatch.setattr(
        "app.logger.get_settings",
        lambda: Settings(llm_api_key=SecretStr(test_key)),
    )

    filter_ = SecretRedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=f"Error connecting with key {test_key} and Bearer sk-ant-api03-1234567890abcdef",
        args=(),
        exc_info=None,
    )

    filter_.filter(record)

    assert test_key not in record.msg
    assert "[REDACTED_API_KEY]" in record.msg
    assert "[REDACTED_SECRET]" in record.msg

