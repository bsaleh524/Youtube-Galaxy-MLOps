"""Embedding parity: local sentence-transformers vs Workers AI REST for BAAI/bge-small-en-v1.5.

Needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (Workers AI permission) in .env.

    uv run python -m pipeline.parity_check [--data path/to/youtubers.json] [--out data/parity_report.json]

Compares, per text, cosine(local, remote) for remote pooling=cls (what we use) and pooling=mean (the API
default, expected to be worse). Passages get no prefix; queries get the bge query prefix on both sides.
Pass: min cosine >= 0.99 with pooling=cls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv

MODEL_LOCAL = "BAAI/bge-small-en-v1.5"
MODEL_REMOTE = "@cf/baai/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # same as worker/src/embed.ts
PASS_THRESHOLD = 0.99

SEED_DATA = Path("../Controversy-Early-Warning-System/data/fandom/youtubers_data_combined.json")
QUERIES = [
    "minecraft let's play creators",
    "who makes speedrun videos",
    "makeup and beauty tutorials",
    "true crime documentary channels",
    "creators who review fast food",
    "video essays about film",
    "Australian gaming youtuber",
    "science experiments for kids",
    "mukbang eating shows",
    "horror game reactions with jump scares",
]


def sample_passages(path: Path, n: int = 20, max_chars: int = 1200) -> list[str]:
    data = json.loads(path.read_text())
    rng = np.random.default_rng(0)
    picks = rng.choice(len(data), n, replace=False)
    out = []
    for i in picks:
        d = data[int(i)]
        out.append(f"{d.get('title', '')} - {(d.get('description') or '')[:max_chars]}")
    return out


def embed_remote(texts: list[str], pooling: str, account: str, token: str) -> np.ndarray:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL_REMOTE}"
    vecs = []
    for i in range(0, len(texts), 10):
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"text": texts[i : i + 10], "pooling": pooling},
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("success", True):
            raise RuntimeError(body)
        vecs.extend(body["result"]["data"])
    v = np.asarray(vecs, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=SEED_DATA)
    ap.add_argument("--out", type=Path, default=Path("data/parity_report.json"))
    a = ap.parse_args()

    load_dotenv()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID"), os.getenv("CLOUDFLARE_API_TOKEN")
    if not account or not token:
        print("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env first.", file=sys.stderr)
        return 2

    from sentence_transformers import SentenceTransformer

    passages = sample_passages(a.data)
    queries = [QUERY_PREFIX + q for q in QUERIES]
    texts = passages + queries

    model = SentenceTransformer(MODEL_LOCAL)
    pooling_cfg = [type(m).__name__ for m in model]
    local = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)

    report: dict = {"model_local": MODEL_LOCAL, "model_remote": MODEL_REMOTE, "local_modules": pooling_cfg}
    for pooling in ("cls", "mean"):
        remote = embed_remote(texts, pooling, account, token)
        cos = (local * remote).sum(1)
        report[pooling] = {
            "passages": {"min": float(cos[: len(passages)].min()), "mean": float(cos[: len(passages)].mean())},
            "queries": {"min": float(cos[len(passages) :].min()), "mean": float(cos[len(passages) :].mean())},
            "min": float(cos.min()),
        }
        # Ranking agreement: top-3 passages per query, local vs remote.
        lq, lp = local[len(passages) :], local[: len(passages)]
        rq, rp = remote[len(passages) :], remote[: len(passages)]
        lt = np.argsort(-(lq @ lp.T), axis=1)[:, :3]
        rt = np.argsort(-(rq @ rp.T), axis=1)[:, :3]
        report[pooling]["top3_overlap"] = float(np.mean([len(set(x) & set(y)) / 3 for x, y in zip(lt, rt)]))

    report["pass"] = report["cls"]["min"] >= PASS_THRESHOLD
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
