"""Command-line interface for alterego."""

import asyncio
import sys

from app.chat_handler import ChatHandler
from app.config import get_settings
from app.logger import logger
from app.telegram import TelegramClient, TelegramError


async def run_telegram_polling() -> None:
    """Run long polling for local development without requiring an HTTPS tunnel."""
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set in your .env file.\n"
            "Please create a bot with @BotFather on Telegram and add the token to .env."
        )
        sys.exit(1)

    client = TelegramClient(config=settings)
    handler = ChatHandler(config=settings, telegram_client=client)

    logger.info("Starting Telegram long polling for persona '%s'...", settings.persona_name)
    logger.info("Press Ctrl+C to stop.")

    offset: int | None = None

    while True:
        try:
            updates = await client.get_updates(offset=offset, timeout=30)
            for update in updates:
                update_id = update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1

                try:
                    await handler.handle_telegram_update(update)
                except Exception as err:
                    logger.error("Error processing update %s: %s", update_id, type(err).__name__)

        except TelegramError as err:
            logger.error("Telegram polling error: %s. Retrying in 5s...", err)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Polling stopped.")
            break
        except Exception as err:
            logger.error("Unexpected polling error: %s. Retrying in 5s...", type(err).__name__)
            await asyncio.sleep(5)


def main() -> None:
    """CLI entrypoint."""
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m app.cli <command>")
        print("Available commands:")
        print("  telegram-poll   Start Telegram long-polling loop for local development")
        sys.exit(1)

    command = args[0]
    if command == "telegram-poll":
        try:
            asyncio.run(run_telegram_polling())
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        print(f"Unknown command: '{command}'")
        print("Available commands: telegram-poll")
        sys.exit(1)


if __name__ == "__main__":
    main()

