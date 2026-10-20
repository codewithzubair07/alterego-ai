"""Tests for Telegram bot integration, webhook security, and message pipeline."""

import logging
from pydantic import SecretStr
import pytest
import respx
import httpx

from app.chat_handler import ChatHandler, ChatState
from app.config import Settings
from app.main import app
from app.telegram import TELEGRAM_MAX_MESSAGE_LENGTH, TelegramClient, split_message


# ------------------------------------------------------------------------------
# Unit tests for message splitting
# ------------------------------------------------------------------------------

def test_split_message_short_text():
    text = "Hello, world!"
    chunks = split_message(text, max_chars=100)
    assert chunks == [text]


def test_split_message_exact_limit():
    text = "a" * 100
    chunks = split_message(text, max_chars=100)
    assert chunks == [text]


def test_split_message_long_text_splits_at_newline():
    p1 = "Paragraph 1 is here."
    p2 = "Paragraph 2 is here."
    combined = f"{p1}\n\n{p2}"
    chunks = split_message(combined, max_chars=len(p1) + 5)
    assert len(chunks) == 2
    assert chunks[0] == p1
    assert chunks[1] == p2


def test_split_message_hard_break_when_no_whitespace():
    long_str = "x" * 5000
    chunks = split_message(long_str, max_chars=TELEGRAM_MAX_MESSAGE_LENGTH)
    assert len(chunks) == 2
    assert len(chunks[0]) == TELEGRAM_MAX_MESSAGE_LENGTH
    assert len(chunks[1]) == 5000 - TELEGRAM_MAX_MESSAGE_LENGTH


# ------------------------------------------------------------------------------
# Webhook authentication & endpoint tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_rejects_when_secret_empty_in_production(mock_settings: Settings, monkeypatch):
    prod_settings = mock_settings.model_copy(
        update={"telegram_webhook_secret": SecretStr(""), "app_env": "production"}
    )
    monkeypatch.setattr("app.main.get_settings", lambda: prod_settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            json={"update_id": 1, "message": {"text": "hi"}},
        )
        assert response.status_code == 403
        assert "Webhook secret is not configured on server" in response.json()["detail"]


@pytest.mark.asyncio
@respx.mock
async def test_webhook_allows_empty_secret_in_development(
    mock_settings: Settings,
    persona_loader,
    monkeypatch,
):
    dev_settings = mock_settings.model_copy(
        update={"telegram_webhook_secret": SecretStr(""), "app_env": "development"}
    )
    monkeypatch.setattr("app.main.get_settings", lambda: dev_settings)
    monkeypatch.setattr("app.chat_handler.get_settings", lambda: dev_settings)

    bot_token = dev_settings.telegram_bot_token.get_secret_value()
    respx.post(dev_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Dev response"}}]},
        )
    )
    respx.post(f"https://api.telegram.org/bot{bot_token}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            json={"update_id": 1, "message": {"chat": {"id": 123}, "text": "hello"}},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_webhook_rejects_missing_secret_token(mock_settings: Settings, monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: mock_settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            json={"update_id": 1, "message": {"text": "hi"}},
        )
        assert response.status_code == 403
        assert "Invalid or missing webhook secret token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret_token(mock_settings: Settings, monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: mock_settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "completely_wrong_secret"},
            json={"update_id": 1, "message": {"text": "hi"}},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
@respx.mock
async def test_webhook_accepts_valid_secret_and_processes(
    mock_settings: Settings,
    persona_loader,
    monkeypatch,
):
    monkeypatch.setattr("app.main.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.chat_handler.get_settings", lambda: mock_settings)

    secret_header = mock_settings.telegram_webhook_secret.get_secret_value()
    bot_token = mock_settings.telegram_bot_token.get_secret_value()

    # Mock LLM response
    respx.post(mock_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "I am doing well!"}}]},
        )
    )

    # Mock Telegram sendChatAction and sendMessage
    respx.post(f"https://api.telegram.org/bot{bot_token}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_message_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 101}})
    )

    payload = {
        "update_id": 12345,
        "message": {
            "message_id": 1,
            "chat": {"id": 998877},
            "text": "How are you?",
        },
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": secret_header},
            json=payload,
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    assert send_message_route.called


# ------------------------------------------------------------------------------
# Shared Handler Tests (Disclosure, Split, Non-text, LLM failure)
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_first_message_includes_disclosure_second_does_not(
    mock_settings: Settings,
    persona_loader,
):
    bot_token = mock_settings.telegram_bot_token.get_secret_value()
    state = ChatState()
    client = TelegramClient(config=mock_settings)
    handler = ChatHandler(
        config=mock_settings,
        persona_loader=persona_loader,
        telegram_client=client,
        state=state,
    )

    # Mock LLM response
    respx.post(mock_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Hello from mock LLM."}}]},
        )
    )

    respx.post(f"https://api.telegram.org/bot{bot_token}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_msg_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    chat_id = 77777

    # First message: should have AI disclosure
    update_1 = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": chat_id}, "text": "Hello!"},
    }
    await handler.handle_telegram_update(update_1)

    assert send_msg_route.call_count == 1
    first_sent_text = send_msg_route.calls[0].request.read().decode("utf-8")
    assert "Hi, I'm an AI version of TestCreator" in first_sent_text
    assert "Hello from mock LLM." in first_sent_text

    # Second message: should NOT have AI disclosure
    update_2 = {
        "update_id": 2,
        "message": {"message_id": 2, "chat": {"id": chat_id}, "text": "What are you doing?"},
    }
    await handler.handle_telegram_update(update_2)

    assert send_msg_route.call_count == 2
    second_sent_text = send_msg_route.calls[1].request.read().decode("utf-8")
    assert "Hi, I'm an AI version of" not in second_sent_text
    assert "Hello from mock LLM." in second_sent_text


@pytest.mark.asyncio
@respx.mock
async def test_long_replies_split_into_multiple_messages(
    mock_settings: Settings,
    persona_loader,
):
    bot_token = mock_settings.telegram_bot_token.get_secret_value()
    state = ChatState()
    client = TelegramClient(config=mock_settings)
    handler = ChatHandler(
        config=mock_settings,
        persona_loader=persona_loader,
        telegram_client=client,
        state=state,
    )

    # 5000 character reply
    long_llm_reply = "A" * 2500 + "\n\n" + "B" * 2500
    respx.post(mock_settings.chat_completions_url).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": long_llm_reply}}]},
        )
    )
    respx.post(f"https://api.telegram.org/bot{bot_token}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_msg_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    update = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 123}, "text": "Tell me a long story."},
    }
    await handler.handle_telegram_update(update)

    # Must be split into at least 2 telegram messages
    assert send_msg_route.call_count >= 2
    for call in send_msg_route.calls:
        req_body = call.request.read().decode("utf-8")
        assert len(req_body) < 4500  # including json wrapper overhead


@pytest.mark.asyncio
@respx.mock
async def test_llm_failure_sends_apology_and_logs_no_secrets(
    mock_settings: Settings,
    persona_loader,
    caplog,
):
    bot_token = mock_settings.telegram_bot_token.get_secret_value()
    llm_key = mock_settings.llm_api_key.get_secret_value()

    state = ChatState()
    client = TelegramClient(config=mock_settings)
    # Set max retries to 0 for immediate failure
    quick_settings = mock_settings.model_copy(update={"llm_max_retries": 0})
    handler = ChatHandler(
        config=quick_settings,
        persona_loader=persona_loader,
        telegram_client=client,
        state=state,
    )

    # Mock LLM failure
    respx.post(quick_settings.chat_completions_url).mock(
        return_value=httpx.Response(500, text=f"Internal Provider Error containing key {llm_key}")
    )
    respx.post(f"https://api.telegram.org/bot{bot_token}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_msg_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    with caplog.at_level(logging.ERROR):
        update = {
            "update_id": 1,
            "message": {"message_id": 1, "chat": {"id": 456}, "text": "Hello bot!"},
        }
        await handler.handle_telegram_update(update)

    # Apology message was sent and includes AI disclosure for the first interaction
    assert send_msg_route.call_count == 1
    sent_text = send_msg_route.calls[0].request.read().decode("utf-8")
    assert "Hi, I'm an AI version of TestCreator" in sent_text
    assert "Sorry, I ran into an issue" in sent_text

    # No secret leaked in logs
    assert llm_key not in caplog.text
    assert bot_token not in caplog.text
    assert "Hello bot!" not in caplog.text  # User message text not in error log


@pytest.mark.asyncio
@respx.mock
async def test_disclosure_sent_once_even_on_llm_failure(
    mock_settings: Settings,
    persona_loader,
):
    bot_token = mock_settings.telegram_bot_token.get_secret_value()
    state = ChatState()
    client = TelegramClient(config=mock_settings)
    quick_settings = mock_settings.model_copy(update={"llm_max_retries": 0})
    handler = ChatHandler(
        config=quick_settings,
        persona_loader=persona_loader,
        telegram_client=client,
        state=state,
    )

    # First attempt: LLM fails (500)
    # Second attempt: LLM succeeds (200)
    respx.post(quick_settings.chat_completions_url).mock(
        side_effect=[
            httpx.Response(500, text="Internal glitch"),
            httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "I am back!"}}]},
            ),
        ]
    )
    respx.post(f"https://api.telegram.org/bot{bot_token}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_msg_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    chat_id = 999

    # Message 1: fails
    await handler.handle_telegram_update({
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": chat_id}, "text": "First message"},
    })
    assert send_msg_route.call_count == 1
    first_reply = send_msg_route.calls[0].request.read().decode("utf-8")
    assert "Hi, I'm an AI version of TestCreator" in first_reply
    assert "Sorry, I ran into an issue" in first_reply

    # Message 2: succeeds, disclosure must NOT be present
    await handler.handle_telegram_update({
        "update_id": 2,
        "message": {"message_id": 2, "chat": {"id": chat_id}, "text": "Second message"},
    })
    assert send_msg_route.call_count == 2
    second_reply = send_msg_route.calls[1].request.read().decode("utf-8")
    assert "Hi, I'm an AI version of" not in second_reply
    assert "I am back!" in second_reply


@pytest.mark.asyncio
@respx.mock
async def test_non_text_update_does_not_crash(
    mock_settings: Settings,
    persona_loader,
):
    bot_token = mock_settings.telegram_bot_token.get_secret_value()
    state = ChatState()
    client = TelegramClient(config=mock_settings)
    handler = ChatHandler(
        config=mock_settings,
        persona_loader=persona_loader,
        telegram_client=client,
        state=state,
    )

    send_msg_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    # Message with photo instead of text
    update = {
        "update_id": 99,
        "message": {
            "message_id": 2,
            "chat": {"id": 888},
            "photo": [{"file_id": "photo_123"}],
        },
    }
    await handler.handle_telegram_update(update)

    # Sends polite clarification
    assert send_msg_route.call_count == 1
    sent_text = send_msg_route.calls[0].request.read().decode("utf-8")
    assert "only read text messages" in sent_text


@pytest.mark.asyncio
@respx.mock
async def test_start_and_help_commands(
    mock_settings: Settings,
    persona_loader,
):
    bot_token = mock_settings.telegram_bot_token.get_secret_value()
    state = ChatState()
    client = TelegramClient(config=mock_settings)
    handler = ChatHandler(
        config=mock_settings,
        persona_loader=persona_loader,
        telegram_client=client,
        state=state,
    )

    send_msg_route = respx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )

    # Test /start
    await handler.handle_telegram_update({
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 10}, "text": "/start"},
    })
    start_body = send_msg_route.calls[0].request.read().decode("utf-8")
    assert "Hi! I'm an AI version of TestCreator" in start_body

    # Test /help
    await handler.handle_telegram_update({
        "update_id": 2,
        "message": {"message_id": 2, "chat": {"id": 10}, "text": "/help"},
    })
    help_body = send_msg_route.calls[1].request.read().decode("utf-8")
    assert "Commands:" in help_body
    assert "/start" in help_body

