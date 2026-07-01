"""FastAPI webhook server — serves bot + web app in production."""

import logging

import uvicorn
from fastapi import FastAPI, Request
from telegram import BotCommand, Update

from bot import build_application
from config import config

logger = logging.getLogger(__name__)

# Build the PTB Application once
_application = build_application()


async def _init_webhook() -> None:
    """Start the PTB application, register webhook + commands."""
    await _application.initialize()

    webhook_url = config.resolved_webhook_url.rstrip("/") + "/webhook"
    await _application.bot.set_webhook(url=webhook_url)

    # Register bot command menu
    commands = [
        BotCommand("start", "Welcome & main menu"),
        BotCommand("help", "Show all commands"),
        BotCommand("draw", "Generate an AI image"),
        BotCommand("generate", "Same as /draw"),
        BotCommand("note", "Save a note or reminder"),
        BotCommand("notes", "List your notes"),
        BotCommand("done", "Mark a note complete"),
        BotCommand("web", "Search the web"),
        BotCommand("search", "Same as /web"),
        BotCommand("new", "Start a fresh conversation"),
        BotCommand("clear", "Wipe conversation history"),
        BotCommand("stats", "Show token usage"),
    ]
    try:
        await _application.bot.set_my_commands(commands)
        logger.info("Bot commands registered (%d)", len(commands))
    except Exception as e:
        logger.warning("Could not register bot commands: %s", e)

    await _application.start()
    logger.info("Webhook registered: %s", webhook_url)


# FastAPI app with webhook + web app routes
app = FastAPI(
    title="Telegram AI Agent",
    description="Personal AI agent with web app dashboard",
    version="1.1.0",
)

# Mount the web app routes
from webapp import router as webapp_router
app.include_router(webapp_router, prefix="/app")


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


@app.get("/")
async def root():
    """Root redirects to web app."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app")


@app.get("/debug-search")
async def debug_search(q: str = "latest AI news") -> dict:
    """Test search backends (diagnostic)."""
    from search_client import search_web, format_search_results
    results = await search_web(q)
    return {
        "query": q,
        "count": len(results),
        "results": [
            {"title": r.title, "url": r.url, "snippet": r.snippet[:100]}
            for r in results
        ],
    }


def run() -> None:
    """Run the FastAPI webhook server."""
    logger.info(
        "Starting server on %s:%s",
        config.WEBHOOK_HOST,
        config.WEBHOOK_PORT,
    )
    uvicorn.run(
        "webhook:app",
        host=config.WEBHOOK_HOST,
        port=config.WEBHOOK_PORT,
        log_level=config.LOG_LEVEL.lower(),
    )
