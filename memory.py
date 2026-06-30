"""Per-user sliding-window conversation memory."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List

from config import config

# A single message in the conversation history
Message = Dict[str, str]  # {"role": "user"|"assistant", "content": "..."}


@dataclass
class Conversation:
    """Tracks a single conversation's history and token usage."""

    chat_id: int
    messages: deque[Message] = field(default_factory=lambda: deque(maxlen=config.MEMORY_SIZE * 2))
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    last_message_at: float = 0.0
    created_at: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the history (pops oldest if over limit)."""
        self.messages.append({"role": role, "content": content})
        self.last_message_at = time.time()

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def get_history(self) -> List[Message]:
        """Return the message list for the API call."""
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @property
    def is_idle(self) -> bool:
        """True if no messages in the last 30 minutes."""
        return time.time() - self.last_message_at > 1800

    @property
    def message_count(self) -> int:
        return len(self.messages) // 2

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


class ConversationMemory:
    """In-memory store of conversations keyed by chat_id."""

    def __init__(self):
        self._store: Dict[int, Conversation] = {}

    def get_or_create(self, chat_id: int) -> Conversation:
        if chat_id not in self._store:
            self._store[chat_id] = Conversation(chat_id=chat_id)
        return self._store[chat_id]

    def get(self, chat_id: int) -> Conversation | None:
        return self._store.get(chat_id)

    def clear(self, chat_id: int) -> bool:
        if chat_id in self._store:
            self._store[chat_id].clear()
            return True
        return False

    def delete(self, chat_id: int) -> bool:
        if chat_id in self._store:
            del self._store[chat_id]
            return True
        return False

    def cleanup_idle(self, max_age: int = 3600) -> int:
        """Remove conversations idle for more than max_age seconds. Returns count removed."""
        now = time.time()
        stale = [cid for cid, conv in self._store.items() if now - conv.last_message_at > max_age]
        for cid in stale:
            del self._store[cid]
        return len(stale)

    @property
    def active_count(self) -> int:
        return len(self._store)


# Singleton
memory = ConversationMemory()
