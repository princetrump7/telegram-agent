"""FastAPI webhook server for production deployments."""

import logging

import uvicorn
from fastapi import FastAPI, Request
from telegram import Update

from bot import build_application
from config import config

logger = logging.getLogger(__name__)

# Build the PTB Application once
_application = build_application()


async def _init_webhook() -> None:
    """Start the PTB application and register the webhook."""
    await _application.initialize()
    webhook_url = config.resolved_webhook_url.rstrip("/") + "/webhook"
    await _application.bot.set_webhook(url=webhook_url)
    logger.info("Webhook registered: %s", webhook_url)
    await _application.start()


app = FastAPI(
    title="Telegram AI Agent",
    description="Claude-powered Telegram assistant",
    version="1.0.0",
)


@app.on_event("startup")
async def startup() -> None:
    await _init_webhook()


@app.on_event("shutdown")
async def shutdown() -> None:
    await _application.stop()
    await _application.shutdown()


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    """Telegram webhook endpoint."""
    json_data = await request.json()
    update = Update.de_json(json_data, _application.bot)
    if update:
        await _application.process_update(update)
    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    bot_info = None
    try:
        bot_info = await _application.bot.get_me()
    except Exception:
        pass
    return {
        "status": "ok",
        "bot": bot_info.username if bot_info else None,
    }


def run() -> None:
    """Run the FastAPI webhook server."""
    logger.info(
        "Starting webhook server on %s:%s",
        config.WEBHOOK_HOST,
        config.WEBHOOK_PORT,
    )
    uvicorn.run(
        "webhook:app",
        host=config.WEBHOOK_HOST,
        port=config.WEBHOOK_PORT,
        log_level=config.LOG_LEVEL.lower(),
    )
