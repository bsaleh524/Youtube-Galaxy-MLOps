"""The exact text each creator is embedded from, and its cache key."""

from __future__ import annotations

import hashlib

DEFAULT_MAX_CHARS = 2000  # ~400-500 tokens; bge-small truncates at 512 tokens anyway


def embed_text(rec: dict, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, bool]:
    """Return (f"{title} - {description}" cut to max_chars on a word boundary, was_truncated)."""
    text = f"{rec['title']} - {rec.get('description') or ''}"
    if len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    if not text[max_chars].isspace():  # the cut splits a word: back off to the last space,
        space = cut.rfind(" ")  # unless that would throw away more than half (one huge token)
        if space > max_chars // 2:
            cut = cut[:space]
    return cut.rstrip(), True


def text_hash(text: str, model_name: str) -> str:
    """Cache key: changes when either the text or the embedding model changes."""
    return hashlib.sha256(f"{model_name}\0{text}".encode()).hexdigest()
