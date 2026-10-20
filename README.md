# alterego

An open-source AI alter ego that chats in your personal voice and style. Self-hostable, provider-agnostic, and designed for creators and developers.

First version configured for **Juber** (`@ArchitectNexus`).

---

## Architecture Overview

1. **Provider Agnostic**: A single async function `llm(messages, config) -> str` connects to any OpenAI-compatible chat completion endpoint (Groq, Google Gemini, OpenRouter, Ollama, OpenAI).
2. **Bring Your Own Key**: All credentials stay in `.env`. Keys are never committed, logged, or returned in API responses.
3. **Persona as Data**: Voice, few-shot examples, facts, and boundary rules live entirely in Markdown files inside `persona/`.
4. **Multi-Channel**: Webhook & polling for Telegram, with Instagram messaging and persistent memory arriving in upcoming stages.

---

## Quickstart

### 1. Installation

Requires Python 3.12+.

```bash
# Clone the repository
git clone <your-repo-url>
cd alterego

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` to configure your LLM provider and bot credentials:

```ini
# Persona name used in greetings and identity disclosures
PERSONA_NAME=Juber

# Default LLM Provider: Groq (Free Tier)
LLM_PROVIDER=groq
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
LLM_API_KEY=gsk_your_groq_api_key_here

# Alternative Provider: Google Gemini (Free Tier via OpenAI-compatible endpoint)
# LLM_PROVIDER=gemini
# LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# LLM_MODEL=gemini-2.0-flash
# LLM_API_KEY=AIzaSy_your_gemini_api_key_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather
TELEGRAM_WEBHOOK_SECRET=generate_a_random_secret_hex_token
```

---

## Setting Up Your Telegram Bot

### Step 1: Create a Bot via @BotFather (Manual Step)
1. Open Telegram and search for [`@BotFather`](https://t.me/BotFather).
2. Send `/newbot`.
3. Follow the prompts to name your bot and choose a username ending in `bot` (e.g., `JuberNexusBot`).
4. `@BotFather` will give you an **API Token** formatted like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`.
5. Paste this token into your `.env` file as `TELEGRAM_BOT_TOKEN`.

### Step 2: Local Development with Long Polling (No Tunnel Required)
For local development and personality tuning without needing an HTTPS tunnel:

```bash
python -m app.cli telegram-poll
```

Open your bot in Telegram, tap **Start**, and test your persona live.

### Step 3: Production Webhook Setup
When ready to deploy your FastAPI server on a public HTTPS URL (e.g., Render, Railway, Cloudflare Tunnel):

1. Generate a random webhook secret token:
   ```bash
   python -c "import secrets; print(secrets.token_hex(24))"
   ```
   Add it to `.env` as `TELEGRAM_WEBHOOK_SECRET`.

2. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. Register your webhook URL with Telegram using `curl`:
   ```bash
   curl -F "url=https://your-domain.com/telegram/webhook" \
        -F "secret_token=your_telegram_webhook_secret" \
        https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook
   ```

4. Verify webhook status anytime:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/getWebhookInfo
   ```

5. When switching back to local polling, delete the webhook:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/deleteWebhook
   ```

---

## Customizing Your Persona

The personality of the bot is defined in the `persona/` folder:

- **`persona/style_guide.md`**: Tone, sentence lengths, slang, words to embrace and words to avoid.
- **`persona/examples.md`**: Few-shot dialogue examples showing authentic replies vs canned robotic responses.
- **`persona/facts.md`**: Tagged markdown sections with facts about your work, tech stack, and background.
- **`persona/rules.md`**: Hard boundaries (AI transparency, no private info, no financial/medical advice).

Each file is currently a placeholder template with `[TODO: fill in ...]` markers ready for your authentic writing.

---

## Running Automated Tests

All tests run fully offline with mocked network requests (no live API keys or network traffic required):

```bash
python -m pytest -v
```

---

## What You Must Do By Hand (Checklist)

- [ ] Obtain a free LLM API key from [GroqCloud](https://console.groq.com/keys) or [Google AI Studio](https://aistudio.google.com/).
- [ ] Create your Telegram bot using `@BotFather` and copy the bot token into `.env`.
- [ ] Fill in your authentic details in `persona/style_guide.md`, `persona/examples.md`, and `persona/facts.md`.
- [ ] If deploying webhooks: obtain an HTTPS domain and register the webhook with `setWebhook`.

---

## License

MIT (c) 2026 Juber

