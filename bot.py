"""Telegram bot handlers — Mira-like personal AI agent."""

import asyncio
import html as html_module
import logging
import time
from typing import Optional, TypeVar

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_client import send_message_with_search_check
from config import config
from image_client import generate_image
from memory import memory
from search_client import format_search_results, search_web
from ui import (
    after_response_keyboard,
    draw_keyboard,
    error_card,
    generation_progress,
    help_card,
    main_menu,
    note_saved_card,
    notes_keyboard,
    notes_list_card,
    response_card,
    safe,
    search_progress,
    search_request_text,
    search_results_card,
    stats_card,
    welcome_card,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
_last_message: dict[int, float] = {}


def _check_rate_limit(chat_id: int) -> Optional[float]:
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


async def _send_long_message(
    update: Update,
    text: str,
    chat_id: int,
    keyboard: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Send a styled message, splitting into chunks of ~4000 chars."""
    MAX_LEN = 4000

    if not text:
        text = "*(empty response)*"

    # First chunk — HTML parsed, with keyboard
    chunk = text[:MAX_LEN]
    await update.message.reply_text(
        chunk,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

    # Remaining chunks — plain text
    pos = MAX_LEN
    while pos < len(text):
        chunk = text[pos : pos + MAX_LEN]
        await update.message.reply_text(chunk, parse_mode=None)
        pos += MAX_LEN


async def _edit_or_send(update: Update, text: str, chat_id: int, keyboard=None):
    """Edit the previous message if possible, otherwise send new."""
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
    except Exception:
        await update.effective_chat.send_message(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )


async def _typing_indicator(chat_id: int, app: Application):
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
        return None


# ---------------------------------------------------------------------------
# Callback query handler (inline keyboard buttons)
# ---------------------------------------------------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data

    logger.debug("Callback from chat %s: %s", chat_id, data)

    # Command callbacks redirect to the actual command handlers
    if data == "cmd_start":
        conv = memory.get_or_create(chat_id)
        await _edit_or_send(update, welcome_card(), chat_id, keyboard=main_menu())
        return

    if data == "cmd_help":
        await _edit_or_send(update, help_card(), chat_id, keyboard=main_menu())
        return

    if data == "cmd_clear":
        memory.clear(chat_id)
        await _edit_or_send(
            update,
            "🗑 <b>Conversation cleared.</b> I've forgotten everything we talked about.",
            chat_id,
            keyboard=main_menu(),
        )
        return

    if data == "cmd_new":
        memory.delete(chat_id)
        memory.get_or_create(chat_id)
        await _edit_or_send(
            update,
            "🆕 <b>Fresh start!</b> What would you like to talk about?",
            chat_id,
            keyboard=main_menu(),
        )
        return

    if data == "cmd_stats":
        conv = memory.get(chat_id)
        if not conv or conv.total_tokens == 0:
            await _edit_or_send(
                update,
                "📊 <b>No data yet.</b>\n\nSend me a message first!",
                chat_id,
                keyboard=main_menu(),
            )
        else:
            await _edit_or_send(
                update,
                stats_card(
                    conv.message_count,
                    conv.total_input_tokens,
                    conv.total_output_tokens,
                    conv.total_tokens,
                    config.AI_MODEL,
                ),
                chat_id,
                keyboard=main_menu(),
            )
        return

    if data == "cmd_notes":
        notes = memory.get_notes(chat_id)
        await _edit_or_send(
            update,
            notes_list_card(notes),
            chat_id,
            keyboard=notes_keyboard(notes) if notes else main_menu(),
        )
        return

    if data == "cmd_web":
        await _edit_or_send(
            update,
            "🔍 <b>Web search</b>\n\nSend me your query like:\n<code>/web latest AI news</code>",
            chat_id,
        )
        return

    if data == "cmd_draw":
        await _edit_or_send(
            update,
            "🎨 <b>Draw an image</b>\n\nSend me your prompt like:\n<code>/draw a cyberpunk cat</code>",
            chat_id,
        )
        return

    if data == "cmd_note":
        await _edit_or_send(
            update,
            "📝 <b>Save a note</b>\n\nSend me your note like:\n<code>/note buy groceries tomorrow</code>",
            chat_id,
        )
        return

    # Done button for notes
    if data.startswith("done_"):
        try:
            note_id = int(data[5:])
            if memory.mark_note_done(note_id):
                notes = memory.get_notes(chat_id)
                await _edit_or_send(
                    update,
                    f"✅ <b>Note #{note_id}</b> marked as done!\n\n"
                    + notes_list_card(notes),
                    chat_id,
                    keyboard=notes_keyboard(notes) if notes else main_menu(),
                )
            else:
                await _edit_or_send(
                    update,
                    f"Couldn't find note #{note_id}.",
                    chat_id,
                    keyboard=main_menu(),
                )
        except (ValueError, IndexError):
            await _edit_or_send(
                update, "Invalid note ID.", chat_id, keyboard=main_menu()
            )
        return

    # Talk more — prompt the user
    if data == "talk_more":
        await _edit_or_send(
            update,
            "💬 Go ahead — I'm listening. What's on your mind?",
            chat_id,
        )
        return


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rich welcome — like Mira's intro card."""
    chat_id = update.effective_chat.id
    memory.get_or_create(chat_id)

    await update.message.reply_text(
        welcome_card(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Styled help with categories."""
    await update.message.reply_text(
        help_card(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation memory."""
    chat_id = update.effective_chat.id
    memory.clear(chat_id)
    logger.info("Cleared history for chat %s", chat_id)
    await update.message.reply_text(
        "🗑 <b>Conversation cleared.</b> I've forgotten everything we talked about.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Styled token usage display."""
    chat_id = update.effective_chat.id
    conv = memory.get(chat_id)

    if not conv or conv.total_tokens == 0:
        await update.message.reply_text(
            "📊 <b>No data yet.</b>\n\nSend me a message first!",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    await update.message.reply_text(
        stats_card(
            conv.message_count,
            conv.total_input_tokens,
            conv.total_output_tokens,
            conv.total_tokens,
            config.AI_MODEL,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start completely fresh."""
    chat_id = update.effective_chat.id
    memory.delete(chat_id)
    memory.get_or_create(chat_id)
    logger.info("Started fresh conversation for chat %s", chat_id)
    await update.message.reply_text(
        "🆕 <b>Fresh start!</b> I've wiped our old conversation completely.\nWhat would you like to talk about?",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------
async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an image with styled progress + result."""
    chat_id = update.effective_chat.id
    prompt = " ".join(context.args) if context.args else ""

    if not prompt:
        await update.message.reply_text(
            "🎨 <b>Draw an image</b>\n\n"
            "Usage: <code>/draw &lt;description&gt;</code>\n"
            "Example: <code>/draw a cyberpunk cat riding a neon motorcycle</code>\n\n"
            "💡 <b>Try being specific</b> — style, lighting, colors make better results!",
            parse_mode=ParseMode.HTML,
        )
        return

    # Show styled progress
    await update.message.reply_text(
        generation_progress(prompt),
        parse_mode=ParseMode.HTML,
    )

    try:
        image_bytes = await asyncio.to_thread(generate_image, prompt)

        conv = memory.get_or_create(chat_id)
        conv.add_message("user", f"[🎨 Image request] {prompt}")
        conv.add_message("assistant", f"[Generated image] {prompt}")

        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"🎨 <i>{safe(prompt[:200])}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=draw_keyboard(),
        )

        logger.info("Image generated for chat %s: %s", chat_id, prompt[:80])

    except Exception as e:
        logger.exception("Image generation failed for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            error_card(str(e)[:200]),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


# ---------------------------------------------------------------------------
# Notes / Reminders
# ---------------------------------------------------------------------------
async def note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save a note with styled confirmation."""
    chat_id = update.effective_chat.id
    text = " ".join(context.args) if context.args else ""

    if not text:
        await update.message.reply_text(
            "📝 <b>Save a note</b>\n\n"
            "Usage: <code>/note &lt;something to remember&gt;</code>\n"
            "Example: <code>/note buy groceries tomorrow</code>\n\n"
            "💡 You can also ask me naturally to save something!",
            parse_mode=ParseMode.HTML,
        )
        return

    title = text[:50] if len(text) > 50 else text
    note_id = memory.add_note(chat_id, text, title)

    conv = memory.get_or_create(chat_id)
    conv.add_message("user", f"[📝 Note saved] {text}")
    conv.add_message("assistant", f"[Note #{note_id} saved]")

    notes = memory.get_notes(chat_id)

    await update.message.reply_text(
        note_saved_card(note_id, text),
        parse_mode=ParseMode.HTML,
        reply_markup=notes_keyboard(notes),
    )
    logger.info("Note %d saved for chat %s", note_id, chat_id)


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active notes with done buttons."""
    chat_id = update.effective_chat.id
    notes = memory.get_notes(chat_id)

    await update.message.reply_text(
        notes_list_card(notes),
        parse_mode=ParseMode.HTML,
        reply_markup=notes_keyboard(notes) if notes else main_menu(),
    )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a note done with styled confirmation."""
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "✅ <b>Complete a note</b>\n\n"
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
        notes = memory.get_notes(chat_id)
        await update.message.reply_text(
            f"✅ <b>Note #{note_id}</b> marked as done! ✨\n\n"
            + notes_list_card(notes),
            parse_mode=ParseMode.HTML,
            reply_markup=notes_keyboard(notes) if notes else main_menu(),
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
    """Search the web with styled results."""
    chat_id = update.effective_chat.id
    query = " ".join(context.args) if context.args else ""

    if not query:
        await update.message.reply_text(
            "🔍 <b>Web search</b>\n\n"
            "Usage: <code>/web &lt;your search query&gt;</code>\n"
            "Example: <code>/web latest AI news 2026</code>\n\n"
            "💡 I also auto-search when you ask about current events!",
            parse_mode=ParseMode.HTML,
        )
        return

    # Show progress
    progress_msg = await update.message.reply_text(
        search_progress(query),
        parse_mode=ParseMode.HTML,
    )

    try:
        results = await search_web(query)

        conv = memory.get_or_create(chat_id)
        conv.add_message("user", f"[🔍 Web search] {query}")
        conv.add_message(
            "assistant",
            f"[Web search results for: {query}]",
        )

        await _send_long_message(
            update,
            search_results_card(query, results),
            chat_id,
            keyboard=search_keyboard(query),
        )

        logger.info("Web search for chat %s: %s | %d results", chat_id, query, len(results))

    except Exception as e:
        logger.exception("Web search failed for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            error_card(str(e)[:200]),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


# ---------------------------------------------------------------------------
# Group chat support
# ---------------------------------------------------------------------------
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages in groups — respond when the bot is @mentioned or replied to."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    message = update.message
    if not message or not message.text:
        return

    bot_user = await context.bot.get_me()
    bot_username = bot_user.username
    user_text = message.text.strip()

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
        return

    # Clean @mention from text
    clean_text = user_text
    if bot_mentioned:
        for variant in [f"@{bot_username}", f"@{bot_username.lower()}", bot_username]:
            clean_text = clean_text.replace(variant, "").strip()

    # Skip commands in groups
    if clean_text.startswith("/"):
        return

    if not clean_text:
        clean_text = user_text

    wait = _check_rate_limit(chat.id)
    if wait:
        return

    conv = memory.get_or_create(chat.id)
    conv.add_message("user", clean_text)

    typing_task = await _typing_indicator(chat.id, context.application)

    try:
        response_text, input_tokens, output_tokens = await asyncio.to_thread(
            send_message_with_search_check, conv
        )

        if response_text.startswith("SEARCH:"):
            query = response_text[7:].strip()
            await update.message.reply_text(search_request_text(conv))
            results = await search_web(query)
            formatted = format_search_results(results, query)
            response_text, in_tok2, out_tok2 = await asyncio.to_thread(
                send_message_with_search_check, conv, formatted
            )
            input_tokens += in_tok2
            output_tokens += out_tok2

        conv.add_tokens(input_tokens, output_tokens)
        conv.add_message("assistant", response_text)

        await _send_long_message(
            update,
            response_card(response_text),
            chat.id,
            keyboard=after_response_keyboard(chat.id),
        )

    except Exception as e:
        logger.exception("Error in group chat %s: %s", chat.id, e)
        try:
            await update.message.reply_text(
                error_card(str(e)[:200]),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    finally:
        if typing_task:
            typing_task.cancel()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acknowledge a photo — no vision support with current model."""
    chat_id = update.effective_chat.id
    caption = update.message.caption or ""

    conv = memory.get_or_create(chat_id)
    note = f"📷 User sent a photo"
    if caption:
        note += f" with caption: {caption}"
    conv.add_message("user", note)
    conv.add_message("assistant", "I can't analyze images with my current model.")

    await update.message.reply_text(
        "📷 <b>Photo received!</b>\n\n"
        "I can't analyze images with the current AI model, but feel free to "
        "describe it or tell me what you need — I'll help however I can! ✨",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a user text message in DMs — with auto-search and styled responses."""
    chat_id = update.effective_chat.id

    # Skip group messages here
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    # Rate limit
    wait = _check_rate_limit(chat_id)
    if wait:
        return

    conv = memory.get_or_create(chat_id)
    conv.add_message("user", user_text)

    typing_task = await _typing_indicator(chat_id, context.application)

    try:
        # Phase 1: Ask AI if it needs current info
        response_text, input_tokens, output_tokens = await asyncio.to_thread(
            send_message_with_search_check, conv
        )

        # Phase 2: Auto-search when AI requests it
        if response_text.startswith("SEARCH:"):
            query = response_text[7:].strip()
            logger.info("AI requested web search for chat %s: %s", chat_id, query)

            await update.message.reply_text(search_request_text(conv))

            results = await search_web(query)
            formatted = format_search_results(results, query)

            response_text, in_tok2, out_tok2 = await asyncio.to_thread(
                send_message_with_search_check, conv, formatted
            )
            input_tokens += in_tok2
            output_tokens += out_tok2

        conv.add_tokens(input_tokens, output_tokens)
        conv.add_message("assistant", response_text)

        await _send_long_message(
            update,
            response_card(response_text),
            chat_id,
            keyboard=after_response_keyboard(chat_id),
        )

        logger.info(
            "Chat %s | %d tokens in | %d tokens out",
            chat_id, input_tokens, output_tokens,
        )

    except Exception as e:
        logger.exception("Error processing message for chat %s: %s", chat_id, e)
        await update.message.reply_text(
            error_card(str(e)[:400]),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )

    finally:
        if typing_task:
            typing_task.cancel()


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler — catches unhandled exceptions."""
    logger.error("Unhandled error: %s", context.error, exc_info=context.error)


# ---------------------------------------------------------------------------
# Build the Application
# ---------------------------------------------------------------------------
def build_application() -> Application:
    """Create and configure the Telegram bot Application with Mira-style UI."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # ── Callback query handler (inline keyboards) ──
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Command handlers ──
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("web", web_search))
    app.add_handler(CommandHandler("search", web_search))

    # ── Image generation ──
    app.add_handler(CommandHandler("draw", draw))
    app.add_handler(CommandHandler("generate", draw))

    # ── Notes / reminders ──
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", list_notes))
    app.add_handler(CommandHandler("done", done))

    # ── Message handlers ──
    # Group chat (mention-based) — must be before general handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_group_message,
    ))

    # Direct messages (text only)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.ChatType.GROUPS,
        handle_message,
    ))

    # Photos
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # ── Error handler ──
    app.add_error_handler(error_handler)

    return app
