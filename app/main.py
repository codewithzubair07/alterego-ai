"""FastAPI application entry point and webhook endpoints."""

from typing import Any
from fastapi import FastAPI, Header, HTTPException, Request, status

from app.chat_handler import ChatHandler
from app.config import get_settings
from app.logger import logger

app = FastAPI(
    title="alterego",
    description="Self-hosted AI alter ego API",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok", "app": "alterego"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
) -> dict[str, bool]:
    """Telegram webhook endpoint. Validates secret token and delegates to shared chat handler."""
    settings = get_settings()
    configured_secret = settings.telegram_webhook_secret.get_secret_value()

    # Verify secret token if configured
    if configured_secret:
        if not x_telegram_bot_api_secret_token or x_telegram_bot_api_secret_token != configured_secret:
            logger.warning("Rejected Telegram webhook request with invalid secret token.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing webhook secret token",
            )

    try:
        update: dict[str, Any] = await request.json()
    except Exception as err:
        logger.error("Failed to parse Telegram webhook JSON: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from err

    handler = ChatHandler(config=settings)
    await handler.handle_telegram_update(update)
    return {"ok": True}

