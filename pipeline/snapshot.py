"""Raw creator snapshots: one immutable directory per scrape, plus a pointer to the current one.

    data/raw/snapshots/<YYYYMMDD-HHMMSS>/creators.json   records sorted by numeric pageid, UTF-8
    data/raw/snapshots/<...>/manifest.json               count, sha256 of creators.json, source, created_at
    data/raw/current                                     text file holding the current snapshot's dir name

Records are keyed by id (`fandom_{pageid}`), never title: different pages can share a title
(e.g. TARGET / Target), and one page may cover several channels by the same creator (issue #2).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

RECORD_KEYS = ("id", "title", "description", "thumbnail", "youtube_url", "url")
ID_RE = re.compile(r"^fandom_\d+$")


def validate_records(records: list[dict]) -> None:
    """Raise ValueError on a missing key, a malformed or duplicate id, or an empty title."""
    seen: set[str] = set()
    for i, r in enumerate(records):
        for key in RECORD_KEYS:
            if key not in r:
                raise ValueError(f"record {i}: missing key '{key}'")
        rid = r["id"]
        if not isinstance(rid, str) or not ID_RE.match(rid):
            raise ValueError(f"record {i}: bad id {rid!r} (want fandom_<pageid>)")
        if rid in seen:
            raise ValueError(f"duplicate id: {rid}")
        seen.add(rid)
        if not isinstance(r["title"], str) or not r["title"].strip():
            raise ValueError(f"record {i} ({rid}): empty title")


def _pageid(record: dict) -> int:
    return int(record["id"].split("_", 1)[1])


def _new_dir(snapshots: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path, n = snapshots / stamp, 1
    while path.exists():  # two snapshots in the same second
        n += 1
        path = snapshots / f"{stamp}-{n}"
    return path


def write_snapshot(records: list[dict], root: Path, source: str) -> Path:
    """Write a new snapshot under root/snapshots/, point root/current at it, return its dir."""
    validate_records(records)
    root = Path(root)
    snap = _new_dir(root / "snapshots")
    tmp = snap.with_name(snap.name + ".tmp")
    tmp.mkdir(parents=True)
    ordered = [{k: r[k] for k in RECORD_KEYS} for r in sorted(records, key=_pageid)]
    data = json.dumps(ordered, ensure_ascii=False, indent=1).encode("utf-8")
    (tmp / "creators.json").write_bytes(data)
    manifest = {
        "count": len(ordered),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source": source,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    tmp.rename(snap)  # a crash never leaves a half-written snapshot under its final name
    pointer = root / "current"
    pointer_tmp = root / "current.tmp"
    pointer_tmp.write_text(snap.name + "\n", encoding="utf-8")
    os.replace(pointer_tmp, pointer)
    return snap


def current_dir(root: Path) -> Path:
    pointer = Path(root) / "current"
    if not pointer.exists():
        raise FileNotFoundError(f"no current snapshot under {root} (run `make seed` first)")
    return Path(root) / "snapshots" / pointer.read_text(encoding="utf-8").strip()


def load_current(root: Path) -> tuple[list[dict], dict]:
    """Return (records, manifest) of the current snapshot."""
    snap = current_dir(root)
    records = json.loads((snap / "creators.json").read_text(encoding="utf-8"))
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    return records, manifest
