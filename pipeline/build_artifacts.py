"""Build one versioned set of site + Worker files from the current snapshot, embeddings and model.

    uv run python -m pipeline.build_artifacts [--out data/artifacts/galaxy]

Writes data/artifacts/galaxy/<version>/ (version = YYYYMMDD-HHMMSS-<first 8 hex of the
embeddings sha256>):

    manifest.json              version, built_at, counts, model, metrics, attribution, inputs
                               (what it was built from; `make pipeline` skips if unchanged), files + sizes
    nodes.json                 columnar {id, title, cluster, x2, y2, x3, y3, z3}; cluster = position in clusters.json
    neighbors.json             {id: [10 ids]}
    clusters.json              [{key, name, colour, size, leader_id, cx2, cy2, cx3, cy3, cz3}]
    details/cluster_<key>.json {id: {bio, source_url, youtube_url, thumbnail}}
    worker/index.bin, centroids.bin, meta.bin, index_manifest.json   (pipeline/index_format.py)

Everything references creators by id; no consumer should rely on row order. Owner names in
data/cluster_names.json are overlaid on the registry, so a rename needs only a rebuild.
The last stdout line is a JSON summary; a size table goes to stderr.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from pipeline import clusterlib
from pipeline.galaxy_model import GalaxyModel
from pipeline.index_format import IndexData, quantize_rows, write_centroids, write_index, write_meta

BIO_CHARS = 500
SNIPPET_CHARS = 400
WORKER_WARN_BYTES = 20 * 1000 * 1000  # issue #1: CPU tail grows with bundle size
WORKER_MAX_BYTES = 60 * 1024 * 1024  # Workers Free script limit is 64 MiB uncompressed
ATTRIBUTION = {
    "source": "YouTube Wiki (Fandom)",
    "source_url": "https://youtube.fandom.com/",
    # https://www.fandom.com/licensing: "Creative Commons Attribution-Share Alike License 3.0 (Unported)"
    # (read by the owner 2026-11-22; Fandom blocks automated fetches of that page).
    "license": "CC BY-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
    "note": "Creator text comes from the YouTube Wiki; each creator links its source page.",
}


def cut(text: str | None, limit: int) -> str:
    """Collapse whitespace; if longer than limit, cut on a word boundary and end with '…'."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    space = head.rfind(" ")
    if space > limit // 2:
        head = head[:space]
    return head.rstrip(" ,;:-") + "…"


def make_version(embeddings_sha256: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{embeddings_sha256[:8]}"


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _detail(r: dict) -> dict:
    d = {
        "bio": cut(r.get("description"), BIO_CHARS),
        "source_url": r["url"],
        "youtube_url": r.get("youtube_url"),
        "thumbnail": r.get("thumbnail"),
    }
    if r.get("missing_from_wiki_since"):  # page vanished from the wiki; kept and flagged (issue #4)
        d["missing_from_wiki_since"] = r["missing_from_wiki_since"]
    return d


def _round(a: np.ndarray) -> list[float]:
    return [round(float(v), 3) for v in a]


def build(
    records: dict[str, dict],
    X: np.ndarray,
    model: GalaxyModel,
    owner_names: dict[str, str],
    out_root: Path,
    version: str,
    inputs: dict | None = None,
) -> Path:
    """Write <out_root>/<version>/ atomically and return it."""
    ids = model.ids
    missing = [rid for rid in ids if rid not in records]
    if missing:
        raise ValueError(f"{len(missing)} model ids missing from the snapshot (e.g. {missing[0]})")
    if len(X) != len(ids):
        raise ValueError(f"embeddings have {len(X)} rows but the model has {len(ids)} ids")
    if model.registry is None or not all(model.meta.get("cluster_keys") or [None]):
        raise ValueError("model has no cluster keys/registry; run `pipeline.cluster --mode fit` first")

    keys = model.meta["cluster_keys"]
    k = len(keys)
    labels = np.asarray(model.labels)
    reg = model.registry["clusters"]
    leaders = clusterlib.leaders(X, labels, model.centroids)

    out_root = Path(out_root)
    final = out_root / version
    tmp = out_root / f".{version}.tmp"
    if final.exists():
        raise FileExistsError(final)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        clusters = []
        for c, key in enumerate(keys):
            members = labels == c
            size = int(members.sum())
            centre = (
                [*_round(model.xy2[members].mean(axis=0)), *_round(model.xyz3[members].mean(axis=0))]
                if size
                else [None] * 5
            )
            clusters.append({
                "key": key,
                "name": owner_names.get(key, reg[key]["name"]),
                "colour": reg[key]["colour"],
                "size": size,
                "leader_id": ids[leaders[c]] if c in leaders else None,
                **dict(zip(("cx2", "cy2", "cx3", "cy3", "cz3"), centre, strict=True)),
            })
        _dump(tmp / "clusters.json", clusters)

        _dump(tmp / "nodes.json", {
            "id": list(ids),
            "title": [records[rid]["title"] for rid in ids],
            "cluster": labels.astype(int).tolist(),
            "x2": _round(model.xy2[:, 0]),
            "y2": _round(model.xy2[:, 1]),
            "x3": _round(model.xyz3[:, 0]),
            "y3": _round(model.xyz3[:, 1]),
            "z3": _round(model.xyz3[:, 2]),
        })
        _dump(tmp / "neighbors.json", {rid: [ids[j] for j in model.neighbors[i]] for i, rid in enumerate(ids)})

        for c, key in enumerate(keys):
            _dump(tmp / "details" / f"cluster_{key}.json", {
                ids[i]: _detail(records[ids[i]]) for i in np.flatnonzero(labels == c)
            })

        # Worker: rows grouped by cluster (stable within a cluster), meta in the same row order.
        order = np.argsort(labels, kind="stable")
        offsets = np.zeros(k + 1, dtype=np.uint32)
        offsets[1:] = np.cumsum(np.bincount(labels, minlength=k))
        q, scales = quantize_rows(X[order])
        w = tmp / "worker"
        w.mkdir()
        write_index(w / "index.bin", IndexData(q, scales, offsets))
        write_centroids(w / "centroids.bin", model.centroids.astype(np.float32))
        write_meta(w / "meta.bin", [
            {
                "id": ids[i],
                "title": records[ids[i]]["title"],
                "cluster": clusters[labels[i]]["name"],
                "url": records[ids[i]]["url"],
                "snippet": cut(records[ids[i]].get("description"), SNIPPET_CHARS),
            }
            for i in order
        ])
        _dump(w / "index_manifest.json", {
            "version": version, "n": len(ids), "dim": int(X.shape[1]), "k": k,
            "model": model.meta["embedding_model"],
        })

        files = {
            p.relative_to(tmp).as_posix(): p.stat().st_size for p in sorted(tmp.rglob("*")) if p.is_file()
        }
        _dump(tmp / "manifest.json", {
            "version": version,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "creators": len(ids),
            "clusters": sum(c["size"] > 0 for c in clusters),
            "embedding_model": model.meta["embedding_model"],
            "metrics": {
                "silhouette": model.meta.get("silhouette"),
                "sizes": clusterlib.size_stats(labels, k),
            },
            "attribution": ATTRIBUTION,
            "inputs": inputs or {},
            "files": files,
        })
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    os.rename(tmp, final)
    return final


def size_report(build_dir: Path) -> dict:
    rows, site, worker = [], [0, 0], [0, 0]
    for p in sorted(Path(build_dir).rglob("*")):
        if not p.is_file():
            continue
        data = p.read_bytes()
        raw, gz = len(data), len(gzip.compress(data, 6))
        rel = p.relative_to(build_dir).as_posix()
        tot = worker if rel.startswith("worker/") else site
        tot[0] += raw
        tot[1] += gz
        if not rel.startswith("details/"):
            rows.append((rel, raw, gz))
    n_details = sum(1 for _ in (Path(build_dir) / "details").glob("*.json"))
    return {"files": rows, "details_files": n_details, "site": site, "worker": worker}


def _mb(b: int) -> str:
    return f"{b / 1e6:8.2f} MB"


def print_sizes(rep: dict) -> None:
    out = sys.stderr
    print(f"{'file':34} {'raw':>11} {'gzip':>11}", file=out)
    for rel, raw, gz in rep["files"]:
        print(f"{rel:34} {_mb(raw)} {_mb(gz)}", file=out)
    print(f"{'(details/: ' + str(rep['details_files']) + ' files, in site total)':34}", file=out)
    print(f"{'SITE total':34} {_mb(rep['site'][0])} {_mb(rep['site'][1])}", file=out)
    print(f"{'WORKER bundle total':34} {_mb(rep['worker'][0])} {_mb(rep['worker'][1])}", file=out)


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings
    from pipeline.embed import load_embeddings
    from pipeline.galaxy_model import load_model
    from pipeline.snapshot import load_current

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None, help="default: <DATA_DIR>/artifacts/galaxy")
    a = ap.parse_args(argv)
    settings = load_settings()
    out = a.out or settings.data_dir / "artifacts" / "galaxy"

    X, ids, rows = load_embeddings(settings.data_dir / "embeddings")
    model = load_model(settings.data_dir / "model" / "galaxy")
    if model.meta.get("embeddings_sha256") != rows["embeddings_sha256"] or model.ids != ids:
        ap.error("model is out of date with the embeddings; run `python -m pipeline.cluster` first")
    records = {r["id"]: r for r in load_current(settings.data_dir / "raw")[0]}
    names_file = settings.data_dir / "cluster_names.json"
    owner = json.loads(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}

    version = make_version(rows["embeddings_sha256"])
    from pipeline.run import current_inputs

    path = build(records, X, model, owner, out, version, inputs=current_inputs(settings.data_dir))
    rep = size_report(path)
    print_sizes(rep)
    if rep["worker"][0] > WORKER_MAX_BYTES:
        print(f"ERROR: Worker bundle {rep['worker'][0]} bytes exceeds {WORKER_MAX_BYTES}", file=sys.stderr)
        return 1
    if rep["worker"][0] > WORKER_WARN_BYTES:
        print("WARNING: Worker bundle over 20 MB (see issue #1, CPU tail)", file=sys.stderr)
    print(json.dumps({"version": version, "path": str(path), "site_bytes": rep["site"][0],
                      "worker_bytes": rep["worker"][0]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
