"""Python mirror of worker/src/names.ts: find the creator a question names ("channels like X").

Kept in step with the Worker by the shared fixture worker/test/fixtures/name_cases.json, which
both tests/test_name_lookup.py and worker/test/names.test.ts run.
"""

from __future__ import annotations

import unicodedata

CUES: list[list[str]] = [
    ["like"],
    ["similar", "to"],
    ["such", "as"],
    ["alternatives", "to"],
    ["alternative", "to"],
    ["resembling"],
    ["than"],
]
FILLER = frozenset({"videos", "video", "content", "channel", "channels", "stuff", "please", "youtube", "on"})
MIN_TITLE = 3


def fold_name(s: str) -> str:
    """NFKD, drop combining marks, lowercase, every run of non-letters/numbers -> one space."""
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.category(ch).startswith("M"))
    out: list[str] = []
    gap = False
    for ch in s.lower():
        if unicodedata.category(ch)[0] in "LN":
            if gap and out:
                out.append(" ")
            out.append(ch)
            gap = False
        else:
            gap = True
    return "".join(out)


def build_name_index(titles: list[str], topic_words: set[str] | frozenset[str] = frozenset()) -> dict[str, int]:
    """Folded title -> lowest row with that title; short titles and topic words are left out."""
    out: dict[str, int] = {}
    for row, title in enumerate(titles):
        key = fold_name(title)
        if len(key) >= MIN_TITLE and key not in topic_words and key not in out:
            out[key] = row
    return out


def _cue_end(words: list[str], i: int) -> int | None:
    for cue in CUES:
        if words[i : i + len(cue)] == cue:
            return i + len(cue)
    return None


def find_named_creator(question: str, names: dict[str, int]) -> int | None:
    words = fold_name(question).split()
    while words and words[-1] in FILLER:
        words.pop()
    if not words:
        return None
    whole = names.get(" ".join(words))
    if whole is not None:
        return whole
    for i in range(len(words)):
        start = _cue_end(words, i)
        if start is None or start >= len(words):
            continue
        row = names.get(" ".join(words[start:]))
        if row is not None:
            return row
    return None
