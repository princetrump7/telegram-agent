"""Telegram bot handlers — commands and message processing."""

import asyncio
import html as html_module
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_client import send_message as ai_send
from config import config
from file_handler import (
    clean_temp_file,
    download_file,
    extract_text_from_file,
    get_file_description,
)
from memory import Conversation, memory
from search_client import format_search_results, search_web

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
_last_message: dict[int, float] = {}


def _check_rate_limit(chat_id: int) -> float | None:
    """Return seconds until the user can send again, or None if OK."""
    now = time.time()
    last = _last_message.get(chat_id, 0.0)
    elapsed = now - last
    if elapsed < config.RATE_LIMIT_SECONDS:
        return round(config.RATE_LIMIT_SECONDS - elapsed, 1)
    _last_message[chat_id] = now
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
T = TypeVar("T")


def _safe_html(text: str) -> str:
    """Escape HTML-special characters so parse_mode=HTML doesn't break."""
    return html_module.escape(text)


async def _send_long_message(
    update: Update,
    text: str,
    chat_id: int,
) -> None:
    """
    Send a long message, splitting into chunks of ~4000 chars.

    Uses HTML parsing only on the first chunk (which is the real response).
    Subsequent chunks are sent as plain text to avoid parse errors from
    broken HTML across the split.
    """
    MAX_LEN = 4000  # leave room below Telegram's 4096 limit

    if not text:
        text = "*(empty response)*"

    # First chunk — HTML parsed
    chunk = text[:MAX_LEN]
    await update.message.reply_text(
        _safe_html(chunk),
        parse_mode=ParseMode.HTML,
    )

    # Remaining chunks — plain text (HTML may be split mid-tag)
    pos = MAX_LEN
    while pos < len(text):
        chunk = text[pos : pos + MAX_LEN]
        await update.message.reply_text(chunk, parse_mode=None)
        pos += MAX_LEN


async def _typing_indicator(chat_id: int, app: Application) -> None:
    """Show a persistent typing indicator while we work."""
    try:
        stop = False

        async def _poke():
            while not stop:
                try:
                    await app.bot.send_chat_action(
                        chat_id=chat_id,
                        action="typing",
                    )
                except Exception:
                    pass
                await asyncio.sleep(4.5)  # Telegram typing expires after ~5s

        task = asyncio.create_task(_poke())
        return task
    except Exception:
        # Best-effort
        pass


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with instructions."""
    chat_id = update.effective_chat.id
    conv = memory.get_or_create(chat_id)

    text = (
        "👋 <b>Hey there! I'm your AI assistant.</b>\n\n"
        "I'm running directly inside Telegram — just send me a message and I'll respond.\n\n"
        "<b>Commands:</b>\n"
        "• <code>/start</code> — this message\n"
        "• <code>/help</code> — show available commands\n"
        "• <code>/clear</code> — reset our conversation\n"
        "• <code>/stats</code> — show token usage\n"
        "• <code>/new</code> — start a fresh conversation\n"
        "• <code>/web &lt;query&gt;</code> — search the web\n\n"
        "<b>New features:</b>\n"
        "📎 Send me a PDF or text file — I'll read and analyze it\n"
        "🌐 Use <code>/web</code> to get current info from the internet\n\n"
        f"<i>Conversation history: {conv.message_count} messages so far</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    text = (
        "<b>Available Commands</b>\n\n"
        "🔹 <code>/start</code> — Welcome & intro\n"
        "🔹 <code>/help</code> — This message\n"
        "🔹 <code>/clear</code> — Wipe conversation history for this chat\n"
        "🔹 <code>/stats</code> — Show how many tokens we've used\n"
        "🔹 <code>/new</code> — Start a completely fresh conversation\n"
        "🔹 <code>/web &lt;query&gt;</code> — Search the web and get AI help\n"
        "🔹 <code>/search &lt;query&gt;</code> — Same as /web\n\n"
        "<b>Tips:</b>\n"
        "• I remember our conversation and refer back to it\n"
        "• You can send me PDFs, text files, code — I'll read and analyze them\n"
        "• Use <code>/clear</code> or <code>/new</code> to reset my memory\n"
        "• Use <code>/web</code> to get current information from the internet\n"
        "• Long responses are split into multiple messages automatically"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation memory for this chat."""
    chat_id = update.effective_chat.id
    memory.clear(chat_id)
    logger.info("Cleared history for chat %s", chat_id)
    await update.message.reply_text(
        "🗑 <b>Conversation history cleared.</b> I've forgotten everything we talked about.",
        parse_mode=ParseMode.HTML,
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show token usage stats."""
    chat_id = update.effective_chat.id
    conv = memory.get(chat_id)

    if not conv or conv.total_tokens == 0:
        await update.message.reply_text(
            "No conversation data yet. Send me a message to get started!"
        )
        return

    text = (
        "<b>📊 Conversation Stats</b>\n\n"
        f"Messages exchanged: <b>{conv.message_count}</b>\n"
        f"Input tokens: <b>{conv.total_input_tokens:,}</b>\n"
        f"Output tokens: <b>{conv.total_output_tokens:,}</b>\n"
        f"Total tokens: <b>{conv.total_tokens:,}</b>\n\n"
        f"<i>Model: {config.AI_MODEL}</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a completely fresh conversation (delete + recreate)."""
    chat_id = update.effective_chat.id
    memory.delete(chat_id)
    memory.get_or_create(chat_id)
    logger.info("Started fresh conversation for chat %s", chat_id)
    await update.message.reply_text(
        "🆕 <b>Fresh start!</b> I've wiped our old conversation completely.\n"
        "What would you like to talk about?",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Web search command
# ---------------------------------------------------------------------------
async def web_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search the web and return AI-summarized results."""
    chat_id = update.effective_chat.id
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text(
            "Usage: <code>/web &lt;your search query&gt;</code>\n"
            "Example: <code>/web latest AI news 2026</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        f"🔍 Searching for: <i>{_safe_html(query)}</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        results = await search_web(query)
        formatted = format_search_results(results, query)

        conv = memory.get_or_create(chat_id)
        conv.add_message("user", f"Web search requested: {query}")
        conv.add_message(
            "assistant",
            f"[Web search results for: {query}]\n\n{formatted}",
        )

        text = f"📄 <b>Results for:</b> {_safe_html(query)}\n\n"
        if not results:
            text += "No results found. Try a different search."
        else:
            for i, r in enumerate(results[:5], 1):
                text += (
                    f"<b>{i}.</b> {_safe_html(r.title)}\n"
                    f"{_safe_html(r.snippet[:200])}\n"
                    f"<code>{_safe_html(r.url[:60])}</code>\n\n"
                )

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

        logger.info("Web search for chat %s: %s | %d results", chat_id, query, len(results))

    except Exception as e:
        logger.exception("Web search failed for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            f"❌ Search failed: {_safe_html(str(e)[:200])}",
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# File / document handlers
# ---------------------------------------------------------------------------
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a document file (PDF, TXT, etc.)."""
    chat_id = update.effective_chat.id
    document = update.message.document

    desc = get_file_description(document)
    await update.message.reply_text(
        f"📎 Received: <i>{_safe_html(desc)}</i>\n⏳ Processing...",
        parse_mode=ParseMode.HTML,
    )

    local_path = await download_file(
        context.application.bot,
        await document.get_file(),
        suffix=Path(document.file_name or "file").suffix or ".tmp",
    )

    if not local_path:
        await update.message.reply_text("❌ Could not download file (too large or error).")
        return

    try:
        text = extract_text_from_file(local_path)

        if not text:
            await update.message.reply_text(
                "📄 File received. I can only analyze text-based files "
                "(.txt, .pdf, .csv, .json, .py, etc.).",
            )
            return

        MAX_CHARS = 10000
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n\n[...content truncated at 10,000 chars]"

        conv = memory.get_or_create(chat_id)
        conv.add_message(
            "user",
            f"File received: {document.file_name or 'unnamed'}\n\n"
            f"File content:\n```\n{text}\n```\n\nPlease analyze this file.",
        )

        # Start typing indicator
        typing_task = await _typing_indicator(chat_id, context.application)

        try:
            response_text, in_tok, out_tok = await asyncio.to_thread(ai_send, conv)
            conv.add_tokens(in_tok, out_tok)
            conv.add_message("assistant", response_text)
            await _send_long_message(update, response_text, chat_id)

            logger.info(
                "File chat %s | %s | %d+%d tokens",
                chat_id,
                document.file_name,
                in_tok,
                out_tok,
            )
        finally:
            if typing_task:
                typing_task.cancel()

    except Exception as e:
        logger.exception("File processing error for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            "❌ Error processing file. Please try again.",
            parse_mode=ParseMode.HTML,
        )
    finally:
        clean_temp_file(local_path)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acknowledge a photo message (vision analysis not available with current model)."""
    chat_id = update.effective_chat.id
    caption = update.message.caption or ""
    photo = update.message.photo[-1]  # Largest size

    conv = memory.get_or_create(chat_id)

    text = f"📷 User sent a photo"
    if caption:
        text += f" with caption: {caption}"
    text += "\n\n(I don't have vision capabilities with the current AI model. Please describe what you'd like help with in text.)"

    conv.add_message("user", text)
    conv.add_message("assistant", "I see you shared a photo. Unfortunately, my current model can't analyze images — but feel free to describe it or tell me what you need!")

    await update.message.reply_text(
        "📷 Photo received! Unfortunately, the current AI model can't analyze images. "
        "Describe what's in it and I'll help.",
    )
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a user text message through Claude."""
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    # Rate limit
    wait = _check_rate_limit(chat_id)
    if wait:
        logger.debug("Rate-limited chat %s for %.1fs", chat_id, wait)
        return

    # Get conversation
    conv = memory.get_or_create(chat_id)

    # Add user message to history
    conv.add_message("user", user_text)

    # Start typing indicator
    typing_task = await _typing_indicator(chat_id, context.application)
    typing_task_started = typing_task is not None

    try:
        # Call AI API
        response_text, input_tokens, output_tokens = await asyncio.to_thread(
            ai_send, conv
        )

        # Update token tracking
        conv.add_tokens(input_tokens, output_tokens)

        # Add assistant response to history
        conv.add_message("assistant", response_text)

        # Send response (split if long)
        await _send_long_message(update, response_text, chat_id)

        logger.info(
            "Chat %s | %d tokens in | %d tokens out | %.1fs",
            chat_id,
            input_tokens,
            output_tokens,
            time.time() - conv.last_message_at,
        )

    except Exception as e:
        logger.exception("Error processing message for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            "🤖 <b>Oops, something went wrong.</b>\n\n"
            f"<code>{_safe_html(str(e)[:200])}</code>\n\n"
            "Please try again in a moment. If this keeps happening, check your API key and connection.",
            parse_mode=ParseMode.HTML,
        )

    finally:
        if typing_task_started:
            typing_task.cancel()


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler — catches unhandled exceptions."""
    logger.error("Unhandled error: %s", context.error, exc_info=context.error)


# ---------------------------------------------------------------------------
# Build the Application
# ---------------------------------------------------------------------------
def build_application() -> Application:
    """Create and configure the Telegram bot Application."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("web", web_search))
    app.add_handler(CommandHandler("search", web_search))

    # Message handler (text only)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # File / document handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Error handler
    app.add_error_handler(error_handler)

    return app
