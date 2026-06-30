"""Handle file downloads and text extraction from Telegram messages."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from telegram import Document, File, PhotoSize
from telegram.ext import Application

logger = logging.getLogger(__name__)

# Max file size for text extraction (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


async def download_file(bot: Application.bot, file: File, suffix: str = "") -> Optional[str]:
    """
    Download a Telegram file to a temp location and return the local path.
    Returns None if the file is too large.
    """
    if file.file_size and file.file_size > MAX_FILE_SIZE:
        logger.warning("File too large: %d bytes", file.file_size)
        return None

    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        await file.download_to_drive(tmp_path)
        logger.info("Downloaded file to %s (%d bytes)", tmp_path, file.file_size or 0)
        return tmp_path
    except Exception as e:
        logger.error("Failed to download file: %s", e)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return None


def extract_text_from_file(file_path: str) -> str:
    """Extract text content from various file types."""
    ext = Path(file_path).suffix.lower()

    try:
        if ext == ".txt":
            return _read_text_file(file_path)

        elif ext == ".pdf":
            return _extract_pdf_text(file_path)

        elif ext in (".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".py", ".js", ".ts", ".html", ".css"):
            return _read_text_file(file_path)

        else:
            return ""
    except Exception as e:
        logger.warning("Error extracting text from %s: %s", file_path, e)
        return ""


def _read_text_file(file_path: str) -> str:
    """Read a plain text file with encoding detection."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception:
            return ""


def _extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""

    try:
        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning("Failed to extract PDF text: %s", e)
        return ""


def get_file_description(document: Document) -> str:
    """Get a human-readable description of a document."""
    parts = []
    if document.file_name:
        parts.append(f"File name: {document.file_name}")
    if document.mime_type:
        parts.append(f"Type: {document.mime_type}")
    if document.file_size:
        size_kb = document.file_size / 1024
        if size_kb > 1024:
            parts.append(f"Size: {size_kb / 1024:.1f} MB")
        else:
            parts.append(f"Size: {size_kb:.0f} KB")
    return " | ".join(parts)


def clean_temp_file(file_path: str) -> None:
    """Safely remove a temporary file."""
    try:
        os.unlink(file_path)
        logger.debug("Cleaned up temp file: %s", file_path)
    except OSError:
        pass
