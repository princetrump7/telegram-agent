"""Persistent per-user conversation memory backed by SQLite.

Survives restarts — the bot remembers you across sessions.
Stores conversation history, user preferences, and notes/reminders.
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from config import config

DATA_DIR = Path.home() / ".telegram-agent"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "memory.db"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_chat
            ON conversations(chat_id, created_at);

        CREATE TABLE IF NOT EXISTS preferences (
            chat_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            created_at REAL NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_notes_chat ON notes(chat_id, done);
    """)
    conn.commit()
    conn.close()


_init_db()


@dataclass
class Conversation:
    """Tracks a single conversation's history and token usage — backed by SQLite."""

    chat_id: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    last_message_at: float = 0.0
    created_at: float = 0.0
    _messages_cache: Optional[List[dict]] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()
        self._load_from_db()

    def _load_from_db(self) -> None:
        conn = _get_db()
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE chat_id = ? ORDER BY created_at",
            (self.chat_id,),
        ).fetchall()
        conn.close()
        self._messages_cache = [{"role": r["role"], "content": r["content"]} for r in rows]

    def add_message(self, role: str, content: str) -> None:
        """Add a message to history and persist to SQLite."""
        now = time.time()
        conn = _get_db()
        conn.execute(
            "INSERT INTO conversations (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (self.chat_id, role, content, now),
        )
        conn.commit()
        conn.close()

        # Keep in-memory cache in sync
        if self._messages_cache is None:
            self._messages_cache = []
        self._messages_cache.append({"role": role, "content": content})
        self.last_message_at = now

        # Trim old messages beyond MEMORY_SIZE * 2
        self._trim_old()

    def _trim_old(self) -> None:
        max_messages = config.MEMORY_SIZE * 2
        if self._messages_cache is None:
            return
        if len(self._messages_cache) <= max_messages:
            return

        # Keep the most recent messages
        excess = len(self._messages_cache) - max_messages
        conn = _get_db()
        conn.execute(
            """DELETE FROM conversations WHERE chat_id = ? AND created_at IN (
                SELECT created_at FROM conversations
                WHERE chat_id = ? ORDER BY created_at LIMIT ?
            )""",
            (self.chat_id, self.chat_id, excess),
        )
        conn.commit()
        conn.close()
        self._messages_cache = self._messages_cache[excess:]

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def get_history(self) -> List[dict]:
        if self._messages_cache is None:
            self._load_from_db()
        return self._messages_cache or []

    def clear(self) -> None:
        conn = _get_db()
        conn.execute("DELETE FROM conversations WHERE chat_id = ?", (self.chat_id,))
        conn.commit()
        conn.close()
        self._messages_cache = []

    @property
    def is_idle(self) -> bool:
        return time.time() - self.last_message_at > 1800

    @property
    def message_count(self) -> int:
        return len(self.get_history()) // 2

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


class ConversationMemory:
    """Persistent conversation store backed by SQLite."""

    def __init__(self):
        pass

    def get_or_create(self, chat_id: int) -> Conversation:
        return Conversation(chat_id=chat_id)

    def get(self, chat_id: int) -> Optional[Conversation]:
        conn = _get_db()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        conn.close()
        if row and row["cnt"] > 0:
            return Conversation(chat_id=chat_id)
        return None

    def clear(self, chat_id: int) -> bool:
        conn = _get_db()
        conn.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
        return True

    def delete(self, chat_id: int) -> bool:
        return self.clear(chat_id)

    def get_preference(self, chat_id: int, key: str, default: str = "") -> str:
        conn = _get_db()
        row = conn.execute(
            "SELECT data FROM preferences WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        conn.close()
        if row:
            data = json.loads(row["data"])
            return data.get(key, default)
        return default

    def set_preference(self, chat_id: int, key: str, value: str) -> None:
        conn = _get_db()
        row = conn.execute(
            "SELECT data FROM preferences WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        now = time.time()
        if row:
            data = json.loads(row["data"])
            data[key] = value
            conn.execute(
                "UPDATE preferences SET data = ?, updated_at = ? WHERE chat_id = ?",
                (json.dumps(data), now, chat_id),
            )
        else:
            conn.execute(
                "INSERT INTO preferences (chat_id, data, updated_at) VALUES (?, ?, ?)",
                (chat_id, json.dumps({key: value}), now),
            )
        conn.commit()
        conn.close()

    def add_note(self, chat_id: int, content: str, title: str = "") -> int:
        conn = _get_db()
        cur = conn.execute(
            "INSERT INTO notes (chat_id, title, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, title, content, time.time()),
        )
        conn.commit()
        note_id = cur.lastrowid
        conn.close()
        return note_id

    def get_notes(self, chat_id: int, include_done: bool = False) -> List[dict]:
        conn = _get_db()
        if include_done:
            rows = conn.execute(
                "SELECT id, title, content, created_at, done FROM notes WHERE chat_id = ? ORDER BY created_at DESC LIMIT 50",
                (chat_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, content, created_at, done FROM notes WHERE chat_id = ? AND done = 0 ORDER BY created_at DESC LIMIT 50",
                (chat_id,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_note_done(self, note_id: int) -> bool:
        conn = _get_db()
        cur = conn.execute("UPDATE notes SET done = 1 WHERE id = ?", (note_id,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def cleanup_idle(self, max_age: int = 86400) -> int:
        conn = _get_db()
        cutoff = time.time() - max_age
        cur = conn.execute(
            "DELETE FROM conversations WHERE created_at < ?", (cutoff,)
        )
        conn.commit()
        conn.close()
        return cur.rowcount

    @property
    def active_count(self) -> int:
        conn = _get_db()
        row = conn.execute(
            "SELECT COUNT(DISTINCT chat_id) as cnt FROM conversations"
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0


memory = ConversationMemory()
