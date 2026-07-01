"""Image generation client — free tier via Pollinations.ai + OpenCode Zen fallback."""

import io
import logging
import urllib.request
from typing import Optional

from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)


def _generate_via_pollinations(prompt: str) -> Optional[bytes]:
    """Generate an image using pollinations.ai (free, no API key needed).

    Returns raw PNG bytes or None on failure.
    """
    from urllib.parse import quote

    encoded = quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "telegram-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        logger.warning("Pollinations.ai image generation failed: %s", e)
        return None


def _generate_via_opencode(prompt: str) -> Optional[bytes]:
    """Generate an image using OpenCode Zen's image endpoint (if available)."""
    try:
        client = OpenAI(
            base_url=config.OPENCODE_BASE_URL,
            api_key=config.OPENCODE_API_KEY,
        )
        response = client.images.generate(
            model="dall-e-3",  # Some providers accept this
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        image_url = response.data[0].url
        if not image_url:
            return None

        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "telegram-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        logger.info("OpenCode image generation not available: %s", e)
        return None


def generate_image(prompt: str) -> bytes:
    """Generate an image from a text prompt.

    Tries: OpenCode Zen → Pollinations.ai (free, always works).
    Returns raw image bytes.

    Raises RuntimeError if all methods fail.
    """
    # Try OpenCode Zen first (if configured — it often doesn't support images)
    data = _generate_via_opencode(prompt)
    if data:
        logger.info("Image generated via OpenCode Zen")
        return data

    # Fall back to pollinations.ai (free, always available)
    data = _generate_via_pollinations(prompt)
    if data:
        logger.info("Image generated via Pollinations.ai")
        return data

    raise RuntimeError(
        "😅 Couldn't generate an image right now. "
        "Both image providers are unreachable. Try again in a moment."
    )
