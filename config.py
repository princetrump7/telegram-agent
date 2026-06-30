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

    # --- System prompt ---
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        (
            "You are a friendly and helpful AI assistant running inside Telegram. "
            "You have a warm, conversational tone. Be concise but thorough. "
            "You keep track of the conversation history and refer back to earlier messages naturally. "
            "You are powered by an AI model."
        ),
    )

    # --- Deployment mode ---
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PORT: int = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8080")))
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")

    # --- Rate limiting ---
    RATE_LIMIT_SECONDS: float = float(os.getenv("RATE_LIMIT_SECONDS", "1.0"))

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # --- Derived ---
    @property
    def is_webhook_mode(self) -> bool:
        return bool(self.WEBHOOK_URL)

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
