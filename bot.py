"""Telegram bot handlers — commands and message processing."""

import asyncio
import html as html_module
import logging
import time
from typing import TypeVar

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_client import send_message as ai_send, send_message_with_search_check
from config import config
from image_client import generate_image
from memory import memory
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
    """Send a long message, splitting into chunks of ~4000 chars."""
    MAX_LEN = 4000

    if not text:
        text = "*(empty response)*"

    chunk = text[:MAX_LEN]
    await update.message.reply_text(
        _safe_html(chunk),
        parse_mode=ParseMode.HTML,
    )

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
                await asyncio.sleep(4.5)

        task = asyncio.create_task(_poke())
        return task
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with instructions."""
    chat_id = update.effective_chat.id
    conv = memory.get_or_create(chat_id)

    text = (
        "👋 <b>Hey! I'm your personal AI agent.</b>\n\n"
        "I turn conversations into action. Memory, generation, search — all inside Telegram.\n\n"
        "<b>Commands:</b>\n"
        "• <code>/start</code> — this message\n"
        "• <code>/help</code> — show available commands\n"
        "• <code>/draw &lt;prompt&gt;</code> — generate an image\n"
        "• <code>/generate &lt;prompt&gt;</code> — same as /draw\n"
        "• <code>/note &lt;text&gt;</code> — save a note/reminder\n"
        "• <code>/notes</code> — list your notes\n"
        "• <code>/done &lt;id&gt;</code> — mark a note complete\n"
        "• <code>/web &lt;query&gt;</code> — search the web\n"
        "• <code>/clear</code> — reset our conversation\n"
        "• <code>/stats</code> — show token usage\n"
        "• <code>/new</code> — start a fresh conversation\n\n"
        "<i>I remember everything across chats. Just talk to me naturally.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    text = (
        "<b>Available Commands</b>\n\n"
        "🔹 <code>/start</code> — Welcome & intro\n"
        "🔹 <code>/help</code> — This message\n"
        "🔹 <code>/draw &lt;prompt&gt;</code> — Generate an AI image\n"
        "🔹 <code>/generate &lt;prompt&gt;</code> — Same as /draw\n"
        "🔹 <code>/note &lt;text&gt;</code> — Save a note or reminder\n"
        "🔹 <code>/notes</code> — List your saved notes\n"
        "🔹 <code>/done &lt;id&gt;</code> — Mark a note as completed\n"
        "🔹 <code>/clear</code> — Wipe conversation history\n"
        "🔹 <code>/stats</code> — Show token usage\n"
        "🔹 <code>/new</code> — Start completely fresh\n"
        "🔹 <code>/web &lt;query&gt;</code> — Search the web\n"
        "🔹 <code>/search &lt;query&gt;</code> — Same as /web\n\n"
        "<b>Tips:</b>\n"
        "• I remember our conversation and refer back to it — even across different chats!\n"
        "• Use <code>/draw</code> to generate images from text\n"
        "• Use <code>/note</code> to save quick reminders\n"
        "• Use <code>/web</code> to get current information from the internet\n"
        "• I automatically search the web when I need current info\n"
        "• In groups, mention me or reply to my message to get my attention"
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
# Image generation
# ---------------------------------------------------------------------------
async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an image from a text prompt."""
    chat_id = update.effective_chat.id
    prompt = " ".join(context.args) if context.args else ""

    if not prompt:
        await update.message.reply_text(
            "Usage: <code>/draw &lt;description&gt;</code>\n"
            "Example: <code>/draw a cyberpunk cat riding a neon motorcycle</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    msg = await update.message.reply_text(
        f"🎨 Generating: <i>{_safe_html(prompt[:300])}</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        image_bytes = await asyncio.to_thread(generate_image, prompt)

        conv = memory.get_or_create(chat_id)
        conv.add_message("user", f"[Image generation request] {prompt}")
        conv.add_message("assistant", "[Generated an image based on your prompt]")

        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"✨ <i>{_safe_html(prompt[:200])}</i>",
            parse_mode=ParseMode.HTML,
        )

        logger.info("Image generated for chat %s: %s", chat_id, prompt[:80])

    except Exception as e:
        logger.exception("Image generation failed for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            f"❌ Image generation failed: {_safe_html(str(e)[:200])}",
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# Notes / Reminders
# ---------------------------------------------------------------------------
async def note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save a note or reminder."""
    chat_id = update.effective_chat.id
    text = " ".join(context.args) if context.args else ""

    if not text:
        await update.message.reply_text(
            "Usage: <code>/note &lt;something to remember&gt;</code>\n"
            "Example: <code>/note buy groceries tomorrow</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Extract a title from the first few words
    title = text[:50] if len(text) > 50 else text
    note_id = memory.add_note(chat_id, text, title)

    conv = memory.get_or_create(chat_id)
    conv.add_message("user", f"[Saved note] {text}")
    conv.add_message("assistant", f"[Note saved with ID {note_id}]")

    await update.message.reply_text(
        f"📝 <b>Note saved!</b> (ID: {note_id})\n\n{_safe_html(text[:300])}",
        parse_mode=ParseMode.HTML,
    )
    logger.info("Note %d saved for chat %s", note_id, chat_id)


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active notes for this chat."""
    chat_id = update.effective_chat.id
    notes = memory.get_notes(chat_id)

    if not notes:
        await update.message.reply_text(
            "📭 No notes yet. Use <code>/note &lt;text&gt;</code> to save one.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = ["<b>📋 Your Notes</b>\n"]
    for n in notes:
        title = _safe_html(n["title"][:60])
        short = _safe_html(n["content"][:100])
        lines.append(
            f"<b>#{n['id']}</b> {title}\n"
            f"{short}…\n"
            f"<i>{time.strftime('%b %d, %H:%M', time.localtime(n['created_at']))}</i>\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a note as completed."""
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: <code>/done &lt;note_id&gt;</code>\n"
            "Use <code>/notes</code> to find the ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        note_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "Please provide a valid note ID (a number).",
        )
        return

    if memory.mark_note_done(note_id):
        await update.message.reply_text(
            f"✅ <b>Note #{note_id}</b> marked as done!",
            parse_mode=ParseMode.HTML,
        )
        logger.info("Note %d completed for chat %s", note_id, chat_id)
    else:
        await update.message.reply_text(
            f"Couldn't find note #{note_id}. Use <code>/notes</code> to see your notes.",
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

        MAX_MSG_LEN = 3800
        text = f"📄 <b>Results for:</b> {_safe_html(query)}\n\n"
        if not results:
            text += "No results found. Try a different search."
        else:
            for i, r in enumerate(results[:5], 1):
                snippet = _safe_html(r.snippet[:200])
                url = _safe_html(r.url[:80])
                entry = (
                    f"<b>{i}.</b> {_safe_html(r.title[:150])}\n"
                    f"{snippet}\n"
                    f"<code>{url}</code>\n\n"
                )
                if len(text) + len(entry) > MAX_MSG_LEN:
                    text += "… <i>(more results truncated)</i>"
                    break
                text += entry

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        logger.info("Web search for chat %s: %s | %d results", chat_id, query, len(results))

    except Exception as e:
        logger.exception("Web search failed for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            f"❌ Search failed: {_safe_html(str(e)[:200])}",
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# Group chat support
# ---------------------------------------------------------------------------
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages in groups — respond when the bot is mentioned or replied to."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return  # Not a group — handled by handle_message instead

    message = update.message
    if not message or not message.text:
        return

    bot_username = (await context.bot.get_me()).username
    user_text = message.text.strip()

    # Check if bot is mentioned or the message is a reply to the bot
    bot_mentioned = (
        f"@{bot_username}" in user_text
        or f"@{bot_username.lower()}" in user_text.lower()
    )
    is_reply_to_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.is_bot
    )

    if not bot_mentioned and not is_reply_to_bot:
        return  # Not talking to us

    # Strip the @mention from the text for cleaner history
    clean_text = user_text
    if bot_mentioned:
        clean_text = user_text.replace(f"@{bot_username}", "").strip()
        clean_text = clean_text.replace(f"@{bot_username.lower()}", "").strip()
        clean_text = clean_text.replace(bot_username, "").strip()

    if not clean_text:
        clean_text = user_text

    # Rate limit
    wait = _check_rate_limit(chat.id)
    if wait:
        logger.debug("Rate-limited group chat %s for %.1fs", chat.id, wait)
        return

    conv = memory.get_or_create(chat.id)
    conv.add_message("user", clean_text)

    typing_task = await _typing_indicator(chat.id, context.application)
    typing_task_started = typing_task is not None

    try:
        response_text, input_tokens, output_tokens = await asyncio.to_thread(
            send_message_with_search_check, conv
        )

        if response_text.startswith("SEARCH:"):
            query = response_text[7:].strip()
            logger.info("AI requested web search for group chat %s: %s", chat.id, query)
            results = await search_web(query)
            formatted = format_search_results(results, query)
            response_text, in_tok2, out_tok2 = await asyncio.to_thread(
                send_message_with_search_check, conv, formatted
            )
            input_tokens += in_tok2
            output_tokens += out_tok2

        conv.add_tokens(input_tokens, output_tokens)
        conv.add_message("assistant", response_text)
        await _send_long_message(update, response_text, chat.id)

        logger.info("Group %s | responded | %d tokens", chat.id, conv.total_tokens)

    except Exception as e:
        logger.exception("Error in group chat %s: %s", chat.id, e)
        err = str(e)
        try:
            await update.message.reply_text(
                f"❌ {_safe_html(err[:400])}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    finally:
        if typing_task_started:
            typing_task.cancel()


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
    """Process a user text message in DMs."""
    chat_id = update.effective_chat.id

    # Skip group messages here — handled by handle_group_message
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        return

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
        # Phase 1: Ask the AI if it needs web search
        response_text, input_tokens, output_tokens = await asyncio.to_thread(
            send_message_with_search_check, conv
        )

        # Check if AI requested a web search
        if response_text.startswith("SEARCH:"):
            query = response_text[7:].strip()
            logger.info("AI requested web search for chat %s: %s", chat_id, query)

            # Notify user
            await update.message.reply_text(
                f"🔍 Searching for current info...",
            )

            # Phase 2: Do the search
            results = await search_web(query)
            formatted = format_search_results(results, query)

            # Phase 3: Get AI answer with search context
            response_text, in_tok2, out_tok2 = await asyncio.to_thread(
                send_message_with_search_check, conv, formatted
            )
            input_tokens += in_tok2
            output_tokens += out_tok2

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
        err = str(e)
        await update.message.reply_text(
            f"❌ <b>Something went wrong.</b>\n\n{_safe_html(err[:400])}",
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

    # Image generation
    app.add_handler(CommandHandler("draw", draw))
    app.add_handler(CommandHandler("generate", draw))

    # Notes / reminders
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", list_notes))
    app.add_handler(CommandHandler("done", done))

    # Group chat handler (must be before the general message handler)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_group_message,
    ))

    # Message handler (text only, DMs)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.ChatType.GROUPS,
        handle_message,
    ))

    # Photo handler (acknowledges images — no vision support)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Error handler
    app.add_error_handler(error_handler)

    return app
