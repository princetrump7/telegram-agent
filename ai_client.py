"""AI client wrapper using OpenCode Zen API (free models available)."""

import logging
import time
from pathlib import Path
from typing import Tuple

from openai import OpenAI, APIError, RateLimitError, AuthenticationError

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


def _load_brain_context() -> str:
    """
    Load the AI Second Brain context files and return as formatted Markdown.
    Returns empty string if disabled or files don't exist.
    """
    if not config.SECOND_BRAIN_ENABLED:
        return ""

    brain_dir = Path(config.SECOND_BRAIN_PATH)
    if not brain_dir.exists():
        logger.debug("Second Brain directory not found: %s", brain_dir)
        return ""

    sections = []
    core_files = ["IDENTITY.md", "VOICE.md", "RULES.md"]

    for filename in core_files:
        filepath = brain_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8").strip()
            label = filename.replace(".md", "")
            sections.append(f"=== {label} ===\n{content}")

    # Load all skills files too
    skills_dir = brain_dir / "skills"
    if skills_dir.exists():
        for skill_file in sorted(skills_dir.glob("*.md")):
            content = skill_file.read_text(encoding="utf-8").strip()
            label = skill_file.stem
            sections.append(f"=== Skill: {label} ===\n{content}")

    # Load relevant work/project context if it exists
    work_dir = brain_dir / "work"
    if work_dir.exists():
        for proj_file in sorted(work_dir.glob("*.md")):
            content = proj_file.read_text(encoding="utf-8").strip()
            label = proj_file.stem
            sections.append(f"=== Project: {label} ===\n{content}")

    if not sections:
        return ""

    return (
        "# AI Second Brain — Personal Context\n\n"
        "The following is persistent context about me (the user). "
        "Use it to personalize every response — my identity, voice, rules, and projects.\n\n"
        + "\n\n".join(sections)
        + "\n\n=== End of Personal Context ==="
    )


def _call_api(client: OpenAI, messages: list[dict], model: str, max_tokens: int, attempt: int = 1) -> Tuple[str, int, int, str]:
    """
    Make a single API call and return (response_text, input_tokens, output_tokens, finish_reason).
    Does NOT catch exceptions — those propagate up.
    """
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )

    choice = response.choices[0]
    msg = choice.message
    raw_content = msg.content
    finish_reason = choice.finish_reason or ""

    # Some models (e.g. DeepSeek-R1 family) put the response in reasoning_content
    # instead of content. Fall back to it if content is empty.
    reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
    if not raw_content and reasoning:
        logger.info("Content was empty — using reasoning_content field instead")
        raw_content = reasoning

    response_text = (raw_content or "").strip()

    usage = response.usage
    total_input = sum(_estimate_tokens(m["content"]) for m in messages)
    input_tokens = usage.prompt_tokens if usage else total_input
    output_tokens = usage.completion_tokens if usage else _estimate_tokens(response_text)

    logger.info(
        "API call #%d | model=%s | finish_reason=%s | input_tokens=%d | output_tokens=%d | text_length=%d",
        attempt, model, finish_reason, input_tokens, output_tokens, len(response_text),
    )

    return response_text, input_tokens, output_tokens, finish_reason


def _build_messages(conversation: Conversation, extra_system: str | None = None) -> list[dict]:
    """Build the message list for the API call from conversation history."""
    messages: list[dict] = []

    brain_context = _load_brain_context()
    if brain_context:
        messages.append({"role": "system", "content": brain_context})

    messages.append({"role": "system", "content": config.SYSTEM_PROMPT})

    if extra_system:
        messages.append({"role": "system", "content": extra_system})

    for msg in conversation.get_history():
        messages.append({"role": msg["role"], "content": msg["content"]})

    return messages


def send_message(conversation: Conversation) -> Tuple[str, int, int]:
    """
    Send the conversation to the AI API and return (response_text, input_tokens, output_tokens).
    Includes retry logic with fallback models when the primary model returns empty responses.

    Raises:
        RuntimeError: if all models fail
    """
    client = _get_client()
    messages = _build_messages(conversation)
    return _call_models_with_retry(client, messages)


def send_message_with_search_check(
    conversation: Conversation,
    search_results: str | None = None,
) -> Tuple[str, int, int]:
    """
    Two-phase AI call with automatic web search:

    Phase 1 — if no search_results provided:
      Ask the model if it needs current info. If it responds with
      'SEARCH: <query>', the caller should do the search and call this
      function again with search_results set.
      If it responds normally, that's the final answer.

    Phase 2 — if search_results provided:
      Feed the search results back to the model and get a final answer
      informed by those results.

    Returns (response_text, input_tokens, output_tokens).
    Raises RuntimeError if all models fail.
    """
    client = _get_client()

    if search_results:
        # --- Phase 2: we have search results, get final answer ---
        extra = (
            "Web search results are provided below. Use them to answer "
            "the user's question with current, accurate information. "
            "Cite sources where appropriate."
        )
        messages = _build_messages(conversation, extra_system=extra)
        messages.append({"role": "system", "content": f"Web search results:\n{search_results[:8000]}"})

        logger.info("Phase 2 — search results provided, getting final answer")
        return _call_models_with_retry(client, messages)

    # --- Phase 1: ask if search is needed ---
    search_instruction = (
        "You have the ability to search the web for current information. "
        "If answering this question would benefit from up-to-date information, "
        "respond with exactly: SEARCH: <your search query>\n"
        "For example: SEARCH: latest AI news 2026\n\n"
        "If you can answer from your training data alone, respond normally."
    )
    messages = _build_messages(conversation, extra_system=search_instruction)

    logger.info("Phase 1 — checking if web search is needed")
    response_text, in_tok, out_tok = _call_models_with_retry(client, messages)

    return response_text, in_tok, out_tok


def _call_models_with_retry(client: OpenAI, messages: list[dict]) -> Tuple[str, int, int]:
    """Try multiple models until one returns a non-empty response. Raises RuntimeError if all fail."""
    models_to_try = [
        config.AI_MODEL,
        "google/gemini-2.0-flash-exp:free",
        "qwen-2-5-72b-instruct-free",
        "llama-3-2-3b-it-free",
    ]

    seen_models = set()
    unique_models = []
    for m in models_to_try:
        if m not in seen_models:
            seen_models.add(m)
            unique_models.append(m)

    last_error = ""
    for attempt_idx, model in enumerate(unique_models, 1):
        try:
            response_text, in_tok, out_tok, finish_reason = _call_api(
                client, messages, model, config.MAX_TOKENS, attempt_idx
            )
            if response_text:
                return response_text, in_tok, out_tok

            logger.warning(
                "Model %s returned empty content (finish_reason=%s). %s",
                model, finish_reason,
                "Trying fallback." if attempt_idx < len(unique_models) else "All models tried.",
            )
            last_error = f"Model returned empty (finish_reason={finish_reason})"

        except RateLimitError as e:
            logger.warning("Rate limited on %s: %s", model, e)
            last_error = f"Rate limited: {e}"
            time.sleep(2)
            continue
        except AuthenticationError as e:
            logger.error("Auth error on %s: %s", model, e)
            last_error = f"Auth error: {e}"
            continue
        except APIError as e:
            logger.warning("API error on %s: %s", model, e)
            last_error = f"API error: {e}"
            continue
        except Exception as e:
            logger.exception("Unexpected error on %s: %s", model, e)
            last_error = f"{type(e).__name__}: {e}"
            continue

    error_msg = (
        "😅 Looks like the AI model I'm using is having trouble right now. "
        "This usually happens when the free model is overloaded or rate-limited.\n\n"
        f"<b>Diagnostics:</b> {last_error[:200]}\n\n"
        "Try again in a moment. If it keeps happening, check your API key "
        "or switch to a different model in the .env file."
    )
    raise RuntimeError(error_msg)
