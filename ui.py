"""Mira-inspired UI — styled messages, inline keyboards, web app integration."""

import html as html_module
from datetime import datetime
from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode

from config import config


def safe(text: str) -> str:
    """Escape HTML-special characters."""
    return html_module.escape(text)


def _webapp_url() -> Optional[str]:
    """Return the configured web app URL, or None.
    Auto-detects from RENDER_EXTERNAL_URL in production."""
    return config.resolved_webapp_url or None


# ---------------------------------------------------------------------------
# Inline keyboards
# ---------------------------------------------------------------------------

def main_menu() -> InlineKeyboardMarkup:
    """Main menu — matches Mira's action-oriented layout."""
    buttons = [
        [
            InlineKeyboardButton("🎨 Draw", callback_data="cmd_draw"),
            InlineKeyboardButton("📝 Note", callback_data="cmd_note"),
        ],
        [
            InlineKeyboardButton("🔍 Search", callback_data="cmd_web"),
            InlineKeyboardButton("📋 Notes", callback_data="cmd_notes"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="cmd_stats"),
            InlineKeyboardButton("🆕 New", callback_data="cmd_new"),
        ],
    ]

    # Add web app button if URL is configured
    webapp = _webapp_url()
    if webapp:
        buttons.append([
            InlineKeyboardButton("🌐 Open App", web_app=WebAppInfo(url=webapp)),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("❓ Help", callback_data="cmd_help"),
            InlineKeyboardButton("🗑 Clear", callback_data="cmd_clear"),
        ])

    return InlineKeyboardMarkup(buttons)


def after_response_keyboard() -> InlineKeyboardMarkup:
    """Quick actions shown after every AI response."""
    buttons = [
        [
            InlineKeyboardButton("💬 Continue", callback_data="talk_more"),
            InlineKeyboardButton("📝 Save note", callback_data="cmd_note"),
        ],
        [
            InlineKeyboardButton("🎨 Draw", callback_data="cmd_draw"),
            InlineKeyboardButton("🔍 Search", callback_data="cmd_web"),
        ],
    ]

    webapp = _webapp_url()
    if webapp:
        buttons.append([
            InlineKeyboardButton("🌐 Open App", web_app=WebAppInfo(url=webapp)),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("📊 Stats", callback_data="cmd_stats"),
            InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
        ])

    return InlineKeyboardMarkup(buttons)


def content_studio_keyboard(prompt: str) -> InlineKeyboardMarkup:
    """Post-generation keyboard — like Mira's content studio."""
    buttons = [
        [
            InlineKeyboardButton("🎨 Draw again", callback_data="cmd_draw"),
            InlineKeyboardButton("📝 New prompt", callback_data="cmd_note"),
        ],
    ]
    webapp = _webapp_url()
    if webapp:
        buttons.append([
            InlineKeyboardButton("🌐 Open Gallery", web_app=WebAppInfo(url=webapp + "?tab=gallery")),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🏠 Menu", callback_data="cmd_start"),
        ])

    return InlineKeyboardMarkup(buttons)


def notes_keyboard(notes: List[dict]) -> InlineKeyboardMarkup:
    """Keyboard with a done-button per note."""
    buttons = []
    for n in notes[:6]:
        label = f"✅ #{n['id']} {n['title'][:20]}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"done_{n['id']}")])

    bottom_row = [InlineKeyboardButton("📝 New note", callback_data="cmd_note")]
    webapp = _webapp_url()
    if webapp:
        bottom_row.append(
            InlineKeyboardButton("🌐 App", web_app=WebAppInfo(url=webapp + "?tab=notes"))
        )
    buttons.append(bottom_row)
    return InlineKeyboardMarkup(buttons)


def search_keyboard(query: str) -> InlineKeyboardMarkup:
    """Post-search keyboard."""
    buttons = [
        [
            InlineKeyboardButton("🔍 Search again", callback_data="cmd_web"),
            InlineKeyboardButton("📝 Save as note", callback_data="cmd_note"),
        ],
        [InlineKeyboardButton("🏠 Menu", callback_data="cmd_start")],
    ]
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Message builders — Mira-style cards
# ---------------------------------------------------------------------------

def welcome_card() -> str:
    """Rich welcome message — Mira-inspired."""
    webapp_line = ""
    if _webapp_url():
        webapp_line = "\n🌐 <b>Dashboard</b> — Full stats & gallery"

    return (
        "✦ <b>Your AI agent is live.</b>\n\n"
        "I turn conversations into action — right inside your messenger. "
        "Memory, images, notes, search. Zero setup.\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "🧠 <b>Memory</b> — I remember everything across chats\n"
        "🎨 <b>Content Studio</b> — /draw generates images\n"
        "📝 <b>Notes</b> — Save & track reminders\n"
        "🔍 <b>Search</b> — Current info, automatically\n"
        "👥 <b>Groups</b> — @mention me anywhere"
        + webapp_line +
        "\n\n━━━━━━━━━━━━━━━━━━━\n\n"
        "Ready when you are 💬"
    )


def help_card() -> str:
    """Structured help with categories."""
    webapp_line = ""
    if _webapp_url():
        webapp_line = "🌐 <code>/app</code> — Open dashboard\n"

    return (
        "━━ <b>✦ Commands ✦</b> ━━\n\n"
        "<b>🎨 CONTENT STUDIO</b>\n"
        "🎨 <code>/draw &lt;prompt&gt;</code> — Generate an image\n"
        "⚡ <code>/generate &lt;prompt&gt;</code> — Same\n\n"
        "<b>📝 NOTES</b>\n"
        "📝 <code>/note &lt;text&gt;</code> — Save a note\n"
        "📋 <code>/notes</code> — List all\n"
        "✅ <code>/done &lt;id&gt;</code> — Mark complete\n\n"
        "<b>🔍 SEARCH</b>\n"
        "🔍 <code>/web &lt;query&gt;</code> — Search the web\n"
        "🌐 <code>/search &lt;query&gt;</code> — Same\n\n"
        "<b>💬 CHAT</b>\n"
        "🆕 <code>/new</code> — Fresh conversation\n"
        "🗑 <code>/clear</code> — Wipe history\n"
        "📊 <code>/stats</code> — Usage & activity\n"
        "❓ <code>/help</code> — This message\n"
        + webapp_line +
        "\n━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <b>Tip:</b> In groups, @mention me or reply to my message!"
    )


def response_card(text: str) -> str:
    """Wrap an AI response with consistent styling."""
    return f"{text}\n\n━━━━━━━━━━━━━━━━━━━"


def content_studio_card(prompt: str) -> str:
    """Card shown while generating — like Mira's Content Studio."""
    return (
        "━━ <b>✦ Content Studio ✦</b> ━━\n\n"
        f"🎨 <b>Prompt:</b>\n"
        f"<i>{safe(prompt[:300])}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "⏳ Rendering your image... this usually takes a few seconds"
    )


def content_studio_caption(prompt: str) -> str:
    """Caption for the generated image."""
    return (
        "━━ <b>✦ Content Studio ✦</b> ━━\n\n"
        f"🎨 <i>{safe(prompt[:200])}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━"
    )


def note_saved_card(note_id: int, text: str) -> str:
    """Formatted note-saved confirmation."""
    return (
        "━━ <b>✦ Note Saved ✦</b> ━━\n\n"
        f"📝 <b>ID:</b> #{note_id}\n"
        f"💬 {safe(text[:200])}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"Use <code>/done {note_id}</code> or tap the ✅ button.\n"
        f"Use <code>/notes</code> to see all."
    )


def notes_list_card(notes: List[dict]) -> str:
    """Formatted notes list."""
    if not notes:
        return (
            "━━ <b>✦ Your Notes ✦</b> ━━\n\n"
            "📭 <b>No notes yet.</b>\n\n"
            "Use <code>/note &lt;text&gt;</code> to save one!"
        )

    lines = ["━━ <b>✦ Your Notes ✦</b> ━━\n"]
    for n in notes:
        title = safe(n["title"][:60])
        dt = datetime.fromtimestamp(n["created_at"]).strftime("%b %d, %H:%M")
        lines.append(f"📌 <b>#{n['id']}</b> {title}\n└ {dt}\n")

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(f"\n📝 <b>{len(notes)} active</b>")
    return "\n".join(lines)


def stats_card(msg_count: int, in_tokens: int, out_tokens: int,
               total_tokens: int, model: str, images: int = 0,
               notes: int = 0) -> str:
    """Formatted stats — now includes images & notes."""
    return (
        "━━ <b>✦ Dashboard ✦</b> ━━\n\n"
        f"💬 <b>Messages:</b> {msg_count}\n"
        f"🎨 <b>Images:</b> {images}\n"
        f"📝 <b>Notes:</b> {notes}\n\n"
        f"📥 <b>Input tokens:</b> {in_tokens:,}\n"
        f"📤 <b>Output tokens:</b> {out_tokens:,}\n"
        f"∑ <b>Total tokens:</b> {total_tokens:,}\n\n"
        f"🧠 <b>Model:</b> {safe(model)}\n\n"
        "━━━━━━━━━━━━━━━━━━━"
    )


def search_progress_card(query: str) -> str:
    """Loading message for web search."""
    return (
        "━━ <b>✦ Searching ✦</b> ━━\n\n"
        f"🔍 <i>{safe(query[:200])}</i>\n\n"
        "🌐 Scanning the web for current info..."
    )


def search_results_card(query: str, results) -> str:
    """Formatted web search results."""
    MAX_MSG_LEN = 3800
    text = (
        f"━━ <b>✦ Search Results ✦</b> ━━\n\n"
        f"📄 <b>{safe(query)}</b>\n\n"
    )

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


def error_card(error_text: str) -> str:
    """Formatted error message."""
    return (
        "━━ <b>✦ Oops ✦</b> ━━\n\n"
        f"😅 {safe(error_text[:300])}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "Try again in a moment. Use <code>/new</code> to reset."
    )


def search_request_text() -> str:
    """Text shown when AI auto-requests a search."""
    return (
        "🔍 Let me look that up for the most current info.\n"
        "Give me a sec..."
    )
