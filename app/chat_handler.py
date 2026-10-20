"""Shared chat processing pipeline for messaging platforms."""

from typing import Any
import httpx

from app.config import Settings, get_settings
from app.llm import llm
from app.logger import logger
from app.persona import PersonaLoader
from app.telegram import TelegramClient


class ChatState:
    """In-memory chat state tracking (upgraded to SQLite in Stage 3)."""

    def __init__(self) -> None:
        self.seen_chats: set[str] = set()

    def is_first_interaction(self, chat_id: str | int) -> bool:
        return str(chat_id) not in self.seen_chats

    def mark_seen(self, chat_id: str | int) -> None:
        self.seen_chats.add(str(chat_id))

    def reset(self) -> None:
        self.seen_chats.clear()


# Global state tracker instance
chat_state = ChatState()


class ChatHandler:
    """Core message handler for alterego."""

    def __init__(
        self,
        config: Settings | None = None,
        persona_loader: PersonaLoader | None = None,
        telegram_client: TelegramClient | None = None,
        state: ChatState | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or get_settings()
        self.persona_loader = persona_loader or PersonaLoader(persona_dir=self.config.persona_dir)
        self.telegram = telegram_client or TelegramClient(config=self.config, client=http_client)
        self.state = state or chat_state
        self.http_client = http_client

    async def handle_telegram_update(self, update: dict[str, Any]) -> None:
        """Process an incoming update object from Telegram."""
        message = update.get("message")
        if not message:
            # Updates like edited_message, inline_query, etc.
            logger.debug("Skipping non-message Telegram update.")
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            logger.warning("Received update without chat_id.")
            return

        # Check for non-text messages
        text = message.get("text")
        if text is None:
            logger.info("Received non-text message in chat %s. Replying politely.", chat_id)
            await self.telegram.send_message(
                chat_id=chat_id,
                text="I can only read text messages right now. Feel free to ask your question in text!",
            )
            return

        text = text.strip()
        persona_name = self.config.persona_name
        is_first = self.state.is_first_interaction(chat_id)

        # Handle commands
        if text.startswith("/start"):
            self.state.mark_seen(chat_id)
            welcome_text = (
                f"Hi! I'm an AI version of {persona_name}. I chat and answer questions in "
                f"{persona_name}'s authentic style.\n\n"
                f"Send me a message or ask me anything! Use /help to see what I can do."
            )
            await self.telegram.send_message(chat_id=chat_id, text=welcome_text)
            return

        if text.startswith("/help"):
            self.state.mark_seen(chat_id)
            help_text = (
                f"I am an AI alter ego of {persona_name}.\n\n"
                f"Commands:\n"
                f"/start - Greeting and introduction\n"
                f"/help - Show this guide\n\n"
                f"You can ask me about projects, ideas, tech, or opinions. "
                f"Please note: I am an AI and cannot make formal commitments or share private data."
            )
            await self.telegram.send_message(chat_id=chat_id, text=help_text)
            return

        # Regular conversation message: trigger typing indicator while processing
        await self.telegram.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # Build persona system prompt
            system_prompt = self.persona_loader.build_system_prompt(persona_name=persona_name)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ]

            raw_reply = await llm(
                messages=messages,
                config=self.config,
                client=self.http_client,
            )

            # Prepend disclosure if first time chatting
            if is_first:
                self.state.mark_seen(chat_id)
                final_reply = f"Hi, I'm an AI version of {persona_name}.\n\n{raw_reply}"
            else:
                final_reply = raw_reply

            await self.telegram.send_message(chat_id=chat_id, text=final_reply)

        except Exception as err:
            # Log error without user message text or keys
            logger.error(
                "Failed to process message for chat %s due to error: %s",
                chat_id,
                type(err).__name__,
            )
            apology = "Sorry, I ran into an issue generating a response right now. Please try again in a moment."
            await self.telegram.send_message(chat_id=chat_id, text=apology)

