"""Mira-inspired UI — styled messages, inline keyboards, card formatting."""

import html as html_module
from datetime import datetime
from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode


def safe(text: str) -> str:
    """Escape HTML-special characters."""
    return html_module.escape(text)


# ---------------------------------------------------------------------------
# Inline keyboards
# ---------------------------------------------------------------------------

def main_menu() -> InlineKeyboardMarkup:
    """Persistent home-command keyboard."""
    kb = [
        [
            InlineKeyboardButton("🎨 Draw", callback_data="cmd_draw"),
            InlineKeyboardButton("📝 Note", callback_data="cmd_note"),
        ],
        [
            InlineKeyboardButton("🔍 Web Search", callback_data="cmd_web"),
            InlineKeyboardButton("📋 Notes", callback_data="cmd_notes"),
        ],
        [
            InlineKeyboardButton("🆕 New Chat", callback_data="cmd_new"),
            InlineKeyboardButton("📊 Stats", callback_data="cmd_stats"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="cmd_help"),
            InlineKeyboardButton("🗑 Clear", callback_data="cmd_clear"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


def after_response_keyboard(chat_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Quick actions shown after every AI response."""
    kb = [
        [
            InlineKeyboardButton("💬 Continue", callback_data="talk_more"),
            InlineKeyboardButton("📝 Save note", callback_data="cmd_note"),
        ],
        [
            InlineKeyboardButton("🎨 Draw image", callback_data="cmd_draw"),
            InlineKeyboardButton("🔍 Search web", callback_data="cmd_web"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


def draw_keyboard() -> InlineKeyboardMarkup:
    """Post-draw quick actions."""
    kb = [
        [
            InlineKeyboardButton("🎨 Draw again", callback_data="cmd_draw"),
            InlineKeyboardButton("📝 Save prompt as note", callback_data="save_prompt_note"),
        ],
        [InlineKeyboardButton("🏠 Menu", callback_data="cmd_start")],
    ]
    return InlineKeyboardMarkup(kb)


def notes_keyboard(notes: List[dict]) -> InlineKeyboardMarkup:
    """Keyboard with a done-button per note."""
    buttons = []
    for n in notes[:8]:  # Max 8 for keyboard size
        label = f"✅ Done #{n['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"done_{n['id']}")])

    if notes:
        buttons.append([InlineKeyboardButton("📝 New note", callback_data="cmd_note")])
    return InlineKeyboardMarkup(buttons)


def search_keyboard(query: str) -> InlineKeyboardMarkup:
    """Post-search keyboard."""
    kb = [
        [
            InlineKeyboardButton("🔍 Search again", callback_data="cmd_web"),
            InlineKeyboardButton("📝 Save result", callback_data="cmd_note"),
        ],
        [InlineKeyboardButton("🏠 Menu", callback_data="cmd_start")],
    ]
    return InlineKeyboardMarkup(kb)


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def welcome_card() -> str:
    """Rich welcome message styled like Mira."""
    return (
        "✨ <b>Your personal AI agent is here.</b>\n\n"
        "I turn conversations into action. Memory, images, search, notes — all inside Telegram.\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "🧠 <b>Memory</b> — I remember everything across chats\n"
        "🎨 <b>Draw</b> — Generate images from text\n"
        "📝 <b>Notes</b> — Save reminders and ideas\n"
        "🔍 <b>Search</b> — Current info from the web\n"
        "👥 <b>Groups</b> — @mention me anywhere\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "Ready when you are. Just say what you need 💬"
    )


def help_card() -> str:
    """Structured help with categories."""
    return (
        "━━ <b>✦ Commands ✦</b> ━━\n\n"
        "━━ <b>GENERATION</b> ━━\n"
        "🎨 <code>/draw &lt;prompt&gt;</code> — Generate an image\n"
        "⚡ <code>/generate &lt;prompt&gt;</code> — Same as /draw\n\n"
        "━━ <b>MEMORY & NOTES</b> ━━\n"
        "📝 <code>/note &lt;text&gt;</code> — Save a note\n"
        "📋 <code>/notes</code> — List your notes\n"
        "✅ <code>/done &lt;id&gt;</code> — Mark note complete\n\n"
        "━━ <b>SEARCH</b> ━━\n"
        "🔍 <code>/web &lt;query&gt;</code> — Search the web\n"
        "🌐 <code>/search &lt;query&gt;</code> — Same as /web\n\n"
        "━━ <b>CHAT</b> ━━\n"
        "🆕 <code>/new</code> — Fresh conversation\n"
        "🗑 <code>/clear</code> — Wipe history\n"
        "📊 <code>/stats</code> — Token usage\n"
        "❓ <code>/help</code> — This message\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <b>Tip:</b> In groups, @mention me or reply to my message!"
    )


def response_card(text: str) -> str:
    """Wrap an AI response with consistent styling."""
    return (
        f"{text}\n\n"
        "━━━━━━━━━━━━━━━━━━━"
    )


def note_saved_card(note_id: int, text: str) -> str:
    """Formatted note-saved confirmation."""
    return (
        "━━ <b>✦ Note Saved ✦</b> ━━\n\n"
        f"📝 <b>ID:</b> #{note_id}\n"
        f"💬 <b>Note:</b> {safe(text[:200])}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"Use <code>/done {note_id}</code> to mark complete, or <code>/notes</code> to see all."
    )


def notes_list_card(notes: List[dict]) -> str:
    """Formatted notes list."""
    if not notes:
        return "📭 <b>No notes saved yet.</b>\n\nUse <code>/note &lt;text&gt;</code> to save one!"

    lines = ["━━ <b>✦ Your Notes ✦</b> ━━\n"]
    for n in notes:
        title = safe(n["title"][:60])
        dt = datetime.fromtimestamp(n["created_at"]).strftime("%b %d, %H:%M")
        lines.append(
            f"📌 <b>#{n['id']}</b> {title}\n"
            f"└ {dt}\n"
        )

    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    lines.append(f"\n📝 <b>{len(notes)} active note{'s' if len(notes) != 1 else ''}</b>")
    return "\n".join(lines)


def stats_card(msg_count: int, in_tokens: int, out_tokens: int, total_tokens: int, model: str) -> str:
    """Formatted stats display."""
    return (
        "━━ <b>✦ Conversation Stats ✦</b> ━━\n\n"
        f"💬 <b>Messages:</b> {msg_count}\n"
        f"📥 <b>Input tokens:</b> {in_tokens:,}\n"
        f"📤 <b>Output tokens:</b> {out_tokens:,}\n"
        f"∑ <b>Total tokens:</b> {total_tokens:,}\n\n"
        f"🧠 <b>Model:</b> {safe(model)}\n\n"
        "━━━━━━━━━━━━━━━━━━━"
    )


def generation_progress(prompt: str) -> str:
    """Loading message for image generation."""
    return (
        "━━ <b>✦ Generating ✦</b> ━━\n\n"
        f"🎨 <i>{safe(prompt[:200])}</i>\n\n"
        "⏳ This usually takes a few seconds..."
    )


def search_progress(query: str) -> str:
    """Loading message for web search."""
    return (
        "━━ <b>✦ Searching ✦</b> ━━\n\n"
        f"🔍 <i>{safe(query[:200])}</i>\n\n"
        "🌐 Scanning the web for current info..."
    )


def search_results_card(query: str, results) -> str:
    """Formatted web search results."""
    MAX_MSG_LEN = 3800
    text = f"━━ <b>✦ Search Results ✦</b> ━━\n\n📄 <b>{safe(query)}</b>\n\n"

    if not results:
        text += "No results found. Try a different search."
        return text

    for i, r in enumerate(results[:5], 1):
        snippet = safe(r.snippet[:200])
        url = safe(r.url[:80])
        entry = (
            f"<b>{i}.</b> {safe(r.title[:150])}\n"
            f"└ {snippet}\n"
            f"└ <code>{url}</code>\n\n"
        )
        if len(text) + len(entry) > MAX_MSG_LEN:
            text += "⋯ <i>(more results truncated)</i>"
            break
        text += entry

    text += "━━━━━━━━━━━━━━━━━━━"
    return text


def error_card(error_text: str, friendly: bool = True) -> str:
    """Formatted error message."""
    if friendly:
        return (
            "━━ <b>✦ Oops ✦</b> ━━\n\n"
            f"😅 <b>Something went wrong.</b>\n\n"
            f"{safe(error_text[:300])}\n\n"
            "━━━━━━━━━━━━━━━━━━━\n\n"
            "Try again in a moment. If it keeps happening, use <code>/new</code> to reset."
        )
    return f"❌ {safe(error_text[:300])}"


def search_request_text(conv) -> str:
    """Text shown when AI auto-requests a search."""
    return (
        "🔍 I need to look that up for the most current info.\n"
        "Give me a sec..."
    )
