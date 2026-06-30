"""Entry point — picks polling (dev) or webhook (production) mode."""

import asyncio
import logging
import sys

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

logger = logging.getLogger("main")


def run_polling() -> None:
    """Run in development mode with long-polling."""
    from bot import build_application

    logger.info("Starting in POLLING mode (development)")
    app = build_application()

    # run_polling() handles its own event loop
    app.run_polling(allowed_updates=["messages"])


def run_webhook() -> None:
    """Run in production mode with FastAPI + webhook."""
    from webhook import run

    logger.info("Starting in WEBHOOK mode (production)")
    run()


def main() -> None:
    if not config.is_configured:
        sys.exit(1)

    print("=" * 45)
    print("  Telegram AI Agent")
    print("  Powered by OpenCode Zen")
    print("=" * 45)
    print()

    if config.is_webhook_mode:
        run_webhook()
    else:
        run_polling()


if __name__ == "__main__":
    main()
