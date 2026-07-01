"""Application configuration via environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # --- AI Provider (OpenCode Zen) ---
    OPENCODE_API_KEY: str = os.getenv("OPENCODE_API_KEY", "")
    OPENCODE_BASE_URL: str = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
    AI_MODEL: str = os.getenv("AI_MODEL", "nemotron-3-ultra-free")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "1024"))

    # --- Conversation memory ---
    MEMORY_SIZE: int = int(os.getenv("MEMORY_SIZE", "20"))

    # --- AI Second Brain ---
    SECOND_BRAIN_PATH: str = os.getenv(
        "SECOND_BRAIN_PATH",
        str(Path.home() / "AI-Second-Brain"),
    )
    SECOND_BRAIN_ENABLED: bool = _bool(
        os.getenv("SECOND_BRAIN_ENABLED", "true")
    )

    # --- System prompt ---
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        (
            "You're a personal AI agent — like Mira — inside Telegram. "
            "Your purpose: turn conversations into action. Be proactive, not passive.\n\n"
            "Your personality is warm, sharp, and slightly playful. You're an enabler — "
            "you help the user get things done. Use emojis sparingly but naturally 🎯\n"
            "Be crisp and conversational. Never robotic.\n\n"
            "CORE BEHAVIORS:\n"
            "1. MEMORY: You remember everything across chats. Refer back naturally. "
            "('Last time we talked about…', 'How did that project go?')\n"
            "2. ACTIONS: When the user talks about something they need to do, "
            "offer to save it as a note. Ask: 'Want me to save that?'\n"
            "3. WEB SEARCH: Proactively search when the user asks about current events, "
            "news, prices, weather, or time-sensitive info. Never guess dates.\n"
            "4. GENERATION: If the user wants an image, tell them to use /draw or /generate.\n"
            "5. FOLLOW-UP: At the end of conversations, offer a next step. "
            "('I'll keep an eye on that. Let me know how it goes!')\n\n"
            "You keep track of conversation history and refer back to it. "
            "You're powered by an AI model — and you enjoy being helpful."
        ),
    )

    # --- Deployment mode ---
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PORT: int = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8080")))
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    RENDER_EXTERNAL_URL: str = os.getenv("RENDER_EXTERNAL_URL", "")

    # --- Rate limiting ---
    RATE_LIMIT_SECONDS: float = float(os.getenv("RATE_LIMIT_SECONDS", "1.0"))

    # --- Image generation ---
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "pollinations")
    IMAGE_WIDTH: int = int(os.getenv("IMAGE_WIDTH", "1024"))
    IMAGE_HEIGHT: int = int(os.getenv("IMAGE_HEIGHT", "1024"))

    # --- Web App (Telegram Web App) ---
    WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")
    WEBAPP_PORT: int = int(os.getenv("WEBAPP_PORT", "8081"))
    WEBAPP_HOST: str = os.getenv("WEBAPP_HOST", "127.0.0.1")

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # --- Derived ---
    @property
    def is_webhook_mode(self) -> bool:
        return bool(self.WEBHOOK_URL or self.RENDER_EXTERNAL_URL)

    @property
    def resolved_webhook_url(self) -> str:
        """Return the effective webhook URL, auto-detecting from Render if needed."""
        if self.WEBHOOK_URL:
            return self.WEBHOOK_URL
        if self.RENDER_EXTERNAL_URL:
            return self.RENDER_EXTERNAL_URL
        return ""

    @property
    def is_configured(self) -> bool:
        errors = []
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN")
        if not self.OPENCODE_API_KEY:
            errors.append("OPENCODE_API_KEY")
        if errors:
            print(f"❌ Missing required env vars: {', '.join(errors)}")
            print(f"   Copy .env.example to .env and fill them in.")
            return False
        return True


# Singleton
config = Config()
