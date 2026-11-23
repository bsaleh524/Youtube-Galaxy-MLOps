"""The exact text each creator is embedded from, and its cache key.

Issue #5: wiki bios open with the creator's names ("Marques Keith Brownlee (born …), also known as
MKBHD, is a …"), and the model only reads ~512 tokens, so vectors ended up encoding names. We
therefore drop that opening lead, remove the creator's own names everywhere, and embed the whole
page as up to `max_chunks` chunks that the embed step averages.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

DEFAULT_MAX_CHARS = 2000  # ~400-500 tokens; bge-small truncates at 512 tokens anyway
DEFAULT_MAX_CHUNKS = 1  # issue #5: averaging whole pages lost topics (docs/NOTES.md 2026-11-23); 8 = whole page
PROTECT_DF = 0.05  # words in >= 5% of bios are topics (Minecraft, Roblox, American), never names
LEAD_WINDOW = 400  # the "Name (born …), better known as X," lead ends at the first verb in here
TEXT_PREP = "v2-clean-chunks"

_WORD = re.compile(r"[^\W_]+")
_LEAD_VERB = re.compile(r"\b(?:is|was|are|were)\b")
_DISAMBIG = re.compile(r"\s*(?:Not to be confused with|For other uses|This article is about)[^.]*\.\s*")
_MONTHS = frozenset(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
)


def protected_words(records: list[dict], min_df: float = PROTECT_DF) -> frozenset[str]:
    """Case-sensitive words that appear in at least `min_df` of all descriptions."""
    df: Counter[str] = Counter()
    for r in records:
        df.update(set(_WORD.findall(r.get("description") or "")))
    floor = min_df * len(records)
    return frozenset(w for w, n in df.items() if n >= floor)


def _strip_disambiguation(text: str) -> str:
    while m := _DISAMBIG.match(text):
        text = text[m.end() :]
    return text


def clean_text(rec: dict, protected: frozenset[str]) -> str:
    """The bio without its opening name lead and without the creator's own names (see module doc)."""
    title = rec["title"]
    text = _strip_disambiguation((rec.get("description") or "").strip())
    m = _LEAD_VERB.search(text[:LEAD_WINDOW])
    lead, body = (text[: m.start()], text[m.start() :]) if m else ("", text)
    terms = {w for w in _WORD.findall(lead) if any(c.isupper() for c in w)}
    terms |= set(_WORD.findall(title))
    terms = {t for t in terms if len(t) >= 3 and t not in _MONTHS and t not in protected}
    patterns = [p for p in (title.strip(), *sorted(terms, key=len, reverse=True)) if p]
    if patterns:
        names = re.compile("|".join(r"(?<!\w)" + re.escape(p) + r"(?!\w)" for p in patterns), re.IGNORECASE)
        body = names.sub(" ", body)
    out = " ".join(body.split())
    return out or title


def chunk_text(text: str, max_chars: int, max_chunks: int) -> tuple[list[str], bool]:
    """Split into chunks of at most `max_chars`, cut on word boundaries; (chunks, text_was_left_over)."""
    chunks: list[str] = []
    text = text.strip()
    while text and len(chunks) < max_chunks:
        if len(text) <= max_chars:
            chunks.append(text)
            text = ""
            break
        cut = text[:max_chars]
        if not text[max_chars].isspace():  # the cut splits a word: back off to the last space,
            space = cut.rfind(" ")  # unless that would throw away more than half (one huge token)
            if space > max_chars // 2:
                cut = cut[:space]
        chunks.append(cut.strip())
        text = text[len(cut) :].lstrip()
    return chunks, bool(text)


def embed_chunks(
    rec: dict,
    protected: frozenset[str],
    max_chars: int = DEFAULT_MAX_CHARS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> tuple[list[str], bool]:
    """The chunks this creator is embedded from, and whether the page was cut short."""
    chunks, cut = chunk_text(clean_text(rec, protected), max_chars, max_chunks)
    return (chunks or [rec["title"] or " "]), cut


def keyword_text(rec: dict, protected: frozenset[str], max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Text for cluster keywords: the first embedded chunk."""
    return embed_chunks(rec, protected, max_chars, 1)[0][0]


def text_hash(chunks: list[str], model_name: str) -> str:
    """Cache key: changes when any chunk or the embedding model changes."""
    return hashlib.sha256(f"{model_name}\0{chr(0x1E).join(chunks)}".encode()).hexdigest()
