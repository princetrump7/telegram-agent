"""Image generation client — saves to disk for gallery + web app."""

import io
import json
import logging
import os
import time
import uuid
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)

# Storage for generated images
IMAGE_DIR = Path.home() / ".telegram-agent" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = IMAGE_DIR / "gallery.json"


def _load_gallery() -> list[dict]:
    """Load the gallery metadata from disk."""
    if METADATA_FILE.exists():
        try:
            return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_gallery(gallery: list[dict]) -> None:
    """Save gallery metadata to disk (keep latest 100)."""
    gallery = gallery[:100]
    METADATA_FILE.write_text(json.dumps(gallery, indent=2), encoding="utf-8")


def _save_image(bytes_data: bytes, prompt: str, source: str) -> str:
    """Save image bytes to disk and record metadata.

    Returns the image filename.
    """
    filename = f"{uuid.uuid4().hex}.png"
    filepath = IMAGE_DIR / filename
    filepath.write_bytes(bytes_data)

    # Record metadata
    gallery = _load_gallery()
    gallery.insert(0, {
        "id": uuid.uuid4().hex,
        "filename": filename,
        "prompt": prompt[:200],
        "source": source,
        "created_at": time.time(),
        "width": config.IMAGE_WIDTH,
        "height": config.IMAGE_HEIGHT,
    })
    _save_gallery(gallery)

    logger.info("Image saved: %s (prompt: %s)", filename, prompt[:60])
    return filename


def get_gallery() -> list[dict]:
    """Return all generated images metadata."""
    return _load_gallery()


def delete_from_gallery(image_id: str) -> bool:
    """Delete an image from the gallery by ID."""
    gallery = _load_gallery()
    for i, img in enumerate(gallery):
        if img["id"] == image_id:
            # Delete file
            filepath = IMAGE_DIR / img["filename"]
            if filepath.exists():
                filepath.unlink()
            # Remove from metadata
            gallery.pop(i)
            _save_gallery(gallery)
            return True
    return False


def _generate_via_pollinations(prompt: str) -> Optional[bytes]:
    """Generate an image using pollinations.ai (free, no API key needed)."""
    encoded = quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={config.IMAGE_WIDTH}&height={config.IMAGE_HEIGHT}&nologo=true"

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
            model="dall-e-3",
            prompt=prompt,
            size=f"{config.IMAGE_WIDTH}x{config.IMAGE_HEIGHT}",
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

    Tries: OpenCode Zen → Pollinations.ai.
    Saves the result to disk for the gallery.
    Returns raw image bytes.

    Raises RuntimeError if all methods fail.
    """
    source = "opencode"
    data = _generate_via_opencode(prompt)
    if not data:
        source = "pollinations"
        data = _generate_via_pollinations(prompt)

    if data:
        _save_image(data, prompt, source)
        logger.info("Image generated via %s", source)
        return data

    raise RuntimeError(
        "😅 Couldn't generate an image right now. "
        "Both image providers are unreachable. Try again in a moment."
    )
