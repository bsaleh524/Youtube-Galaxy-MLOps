"""
GTE-Large Embedding Microservice

Wraps Alibaba-NLP/gte-large-en-v1.5 in a tiny FastAPI service.
Called by the chatbot for free-form query embedding.

Results are Redis-cached for 1 hour (same queries → same vector).
"""

import hashlib
import json
import os
from functools import lru_cache

import redis
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI(title="Galaxy Embedding Service")

MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "Alibaba-NLP/gte-large-en-v1.5")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))


def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    device = get_device()
    print(f"Loading {MODEL_NAME} on {device}...")
    model = SentenceTransformer(MODEL_NAME, trust_remote_code=True, device=device)
    print("Model ready")
    return model


@lru_cache(maxsize=1)
def get_redis():
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        return r
    except Exception:
        print("Redis unavailable — caching disabled")
        return None


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: list[float]
    cached: bool
    model: str


@app.on_event("startup")
async def startup():
    # Pre-load the model on startup to avoid cold-start latency on first request
    get_model()


@app.get("/health")
async def health():
    device = get_device()
    return {"status": "ok", "model": MODEL_NAME, "device": device}


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """Embed a text string. Returns a 1024-dim float list."""
    cache_key = f"embed:{hashlib.sha256(request.text.encode()).hexdigest()}"
    r = get_redis()

    # Try cache first
    if r:
        cached = r.get(cache_key)
        if cached:
            return EmbedResponse(
                embedding=json.loads(cached),
                cached=True,
                model=MODEL_NAME,
            )

    # Compute embedding
    model = get_model()
    vector = model.encode(request.text, normalize_embeddings=True).tolist()

    # Store in cache
    if r:
        r.setex(cache_key, CACHE_TTL, json.dumps(vector))

    return EmbedResponse(embedding=vector, cached=False, model=MODEL_NAME)


@app.post("/embed-batch")
async def embed_batch(texts: list[str]):
    """Embed multiple texts at once (more efficient than N single calls)."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return {"embeddings": vectors.tolist(), "model": MODEL_NAME}
