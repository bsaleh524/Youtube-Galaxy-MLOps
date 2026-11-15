"""Check that Workers AI embeddings match local sentence-transformers embeddings.

    uv run python -m pipeline.parity_check [--pooling cls|mean]

Passages are embedded as-is; queries get the bge query prefix, exactly as the Worker does.
Exit codes: 0 parity (min cosine >= 0.99), 1 mismatch, 2 missing settings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

from pipeline.config import load_settings, require

SAMPLES = Path(__file__).with_name("parity_samples.yaml")
THRESHOLD = 0.99


def cosine_rows(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a / np.linalg.norm(a, axis=1, keepdims=True)
    b = b / np.linalg.norm(b, axis=1, keepdims=True)
    return np.sum(a * b, axis=1)


def load_samples(path: Path = SAMPLES) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def embed_local(texts: list[str], model_name: str) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=_device())
    return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pooling", choices=["cls", "mean"], default="cls")
    args = ap.parse_args(argv)

    settings = load_settings()
    try:
        require(settings, "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    from pipeline.workers_ai import embed_remote

    samples = load_samples()
    passages = [p["text"] for p in samples["passages"]]
    queries = [settings.query_prefix + q for q in samples["queries"]]
    labels = [p["id"] for p in samples["passages"]] + [f"q: {q}" for q in samples["queries"]]
    texts = passages + queries

    local = embed_local(texts, settings.embedding_model)
    remote = embed_remote(texts, settings, pooling=args.pooling)
    cos = cosine_rows(local, remote)

    print(f"pooling={args.pooling}  model={settings.embedding_model}")
    for label, c in zip(labels, cos, strict=True):
        print(f"  {c:.5f}  {label[:70]}")
    print(f"min {cos.min():.5f}  mean {cos.mean():.5f}  threshold {THRESHOLD}")
    ok = bool(cos.min() >= THRESHOLD)
    print("PARITY OK" if ok else "PARITY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
