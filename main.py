"""Entry point — picks polling (dev) or webhook (production) mode."""

import asyncio
import logging
import sys
import threading

# Fix for Windows event loop in Python 3.12+
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config import config

# Configure logging early
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=config.LOG_LEVEL,
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Quiet noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)

logger = logging.getLogger("main")


async def setup_commands(app) -> None:
    """Register the bot command menu with Telegram."""
    from telegram import BotCommand

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
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands registered (%d)", len(commands))
    except Exception as e:
        logger.warning("Could not register bot commands: %s", e)


def start_webapp() -> None:
    """Start the web app server in a background thread (dev mode)."""
    from webapp import run_webapp

    logger.info("Web App server starting on http://%s:%s/app", config.WEBAPP_HOST, config.WEBAPP_PORT)
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()
    return t


def run_polling() -> None:
    """Run in development mode with long-polling + web app."""
    from bot import build_application

    logger.info("Starting in POLLING mode (development)")

    # Start the web app server in background
    if config.WEBAPP_URL:
        start_webapp()
    else:
        logger.info("Web App disabled (set WEBAPP_URL to enable)")

    app = build_application()
    app.post_init = setup_commands
    app.run_polling(allowed_updates=["messages"])


def run_webhook() -> None:
    """Run in production mode with FastAPI + webhook + web app."""
    from webhook import run

    logger.info("Starting in WEBHOOK mode (production)")
    run()


def main() -> None:
    if not config.is_configured:
        sys.exit(1)

    print("=" * 50)
    print("  ✦ Telegram AI Agent")
    print("  Your AI agent, inside your messenger")
    if config.WEBAPP_URL:
        print(f"  🌐 {config.WEBAPP_URL}")
    print("=" * 50)
    print()

    if config.is_webhook_mode:
        run_webhook()
    else:
        run_polling()


if __name__ == "__main__":
    main()
