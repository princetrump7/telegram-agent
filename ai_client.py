"""AI client wrapper using OpenCode Zen API (free models available)."""

import logging
from typing import Tuple

from openai import OpenAI

from config import config
from memory import Conversation

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.OPENCODE_BASE_URL,
            api_key=config.OPENCODE_API_KEY,
            default_headers={
                "HTTP-Referer": "https://github.com/princ/telegram-agent",
                "X-Title": "Telegram AI Agent",
            },
        )
    return _client


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def send_message(conversation: Conversation) -> Tuple[str, int, int]:
    """
    Send the conversation to OpenRouter and return (response_text, input_tokens, output_tokens).

    Raises:
        openai.RateLimitError: on quota/rate limits
        openai.AuthenticationError: on bad API key
        openai.APIError: on API failures
    """
    client = _get_client()

    # Build OpenAI-format messages
    messages: list[dict] = [
        {"role": "system", "content": config.SYSTEM_PROMPT},
    ]
    for msg in conversation.get_history():
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    total_input = sum(
        _estimate_tokens(m["content"])
        for m in messages
    )

    logger.info(
        "Sending to OpenCode Zen | model=%s | messages=%d | max_tokens=%d",
        config.AI_MODEL,
        len(messages),
        config.MAX_TOKENS,
    )

    response = client.chat.completions.create(
        model=config.AI_MODEL,
        messages=messages,
        max_tokens=config.MAX_TOKENS,
    )

    choice = response.choices[0]
    response_text = choice.message.content.strip()

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else total_input
    output_tokens = usage.completion_tokens if usage else _estimate_tokens(response_text)

    logger.info(
        "OpenCode Zen responded | input_tokens=%d | output_tokens=%d | text_length=%d",
        input_tokens,
        output_tokens,
        len(response_text),
    )

    return response_text, input_tokens, output_tokens
