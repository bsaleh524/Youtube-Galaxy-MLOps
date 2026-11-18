"""Import the seed scrape as the first snapshot, and the old app's cluster names.

    uv run python -m pipeline.seed [--source-json PATH] [--source-parquet PATH]

Reads (never modifies) the sibling repo. Writes data/raw/snapshots/<stamp>/ (source "seed") and
data/seed/seed_cluster_names.json ({id: cluster_name}). Name matching is by id, never title.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.config import load_settings
from pipeline.snapshot import validate_records, write_snapshot

SIBLING = Path("../Controversy-Early-Warning-System")
DEFAULT_JSON = SIBLING / "data/fandom/youtubers_data_combined.json"
DEFAULT_PARQUET = SIBLING / "data/processed/plotly/starmap_data.parquet"
MAX_UNKNOWN_SHARE = 0.005  # parquet ids missing from the JSON; above this the two don't match


def check_overlap(record_ids: set[str], named: dict[str, str]) -> dict:
    """Compare snapshot ids with seed-name ids. Raises ValueError if they clearly don't belong together."""
    unknown = sorted(set(named) - record_ids)
    unnamed = sorted(record_ids - set(named))
    share = len(unknown) / len(named) if named else 1.0
    if share > MAX_UNKNOWN_SHARE:
        raise ValueError(
            f"{len(unknown)} of {len(named)} named ids ({share:.1%}) are not in the snapshot; "
            "wrong parquet for this JSON?"
        )
    return {
        "records": len(record_ids),
        "named": len(named),
        "names": len(set(named.values())),
        "named_not_in_snapshot": len(unknown),
        "snapshot_without_name": len(unnamed),
    }


def read_seed_names(parquet: Path) -> dict[str, str]:
    import pandas as pd

    df = pd.read_parquet(parquet, columns=["id", "cluster_name"])
    if df["id"].duplicated().any():
        raise ValueError("seed parquet has duplicate ids")
    return dict(zip(df["id"].astype(str), df["cluster_name"].astype(str), strict=True))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--source-parquet", type=Path, default=DEFAULT_PARQUET)
    a = ap.parse_args(argv)
    data_dir = load_settings().data_dir

    records = json.loads(a.source_json.read_text(encoding="utf-8"))
    validate_records(records)
    named = read_seed_names(a.source_parquet)
    report = check_overlap({r["id"] for r in records}, named)

    snap = write_snapshot(records, data_dir / "raw", source="seed")
    out = data_dir / "seed" / "seed_cluster_names.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(sorted(named.items())), ensure_ascii=False, indent=1), encoding="utf-8")

    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({**report, "snapshot": str(snap), "sha256": manifest["sha256"], "names_file": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
