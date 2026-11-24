"""Minimal Workers AI REST client (embeddings only), used by the local parity check."""

from __future__ import annotations

import numpy as np
import requests

from pipeline.config import Settings, require

USER_AGENT = "galaxy-hobby-scraper/1.0"
# Local sentence-transformers model name → Workers AI model id.
WORKERS_MODEL_IDS = {"BAAI/bge-small-en-v1.5": "@cf/baai/bge-small-en-v1.5"}
POOLINGS = ("cls", "mean")
BATCH_SIZE = 20


def embed_remote(texts: list[str], settings: Settings, pooling: str = "cls") -> np.ndarray:
    """Embed texts with Workers AI; returns float32 L2-normalised rows (len(texts), dim)."""
    if pooling not in POOLINGS:
        raise ValueError(f"pooling must be one of {POOLINGS}, got {pooling!r}")
    require(settings, "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
    model = WORKERS_MODEL_IDS[settings.embedding_model]
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/ai/run/{model}"
    )
    headers = {
        "Authorization": f"Bearer {settings.cloudflare_api_token}",
        "User-Agent": USER_AGENT,
    }
    rows: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        resp = requests.post(
            url,
            headers=headers,
            json={"text": texts[i : i + BATCH_SIZE], "pooling": pooling},
            timeout=60,
        )
        resp.raise_for_status()
        rows.extend(resp.json()["result"]["data"])
    out = np.asarray(rows, dtype=np.float32)
    return out / np.linalg.norm(out, axis=1, keepdims=True)
