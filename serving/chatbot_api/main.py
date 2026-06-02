"""
Galaxy Chatbot API
FastAPI service with streaming RAG responses.

Endpoints:
  GET  /health                    — liveness probe
  POST /chat/query                — RAG chatbot (SSE streaming)
  GET  /api/rankings              — current ranking data from Feast
  POST /api/admin/reload          — trigger Weaviate reload from new Parquet
"""

import asyncio
import json
import os
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rag_pipeline import RAGPipeline

app = FastAPI(title="Galaxy Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

pipeline = RAGPipeline()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "changeme")


# ── Request / Response models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

class ReloadRequest(BaseModel):
    parquet_s3_path: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "llm_backend": os.environ.get("LLM_BACKEND", "groq")}


@app.post("/chat/query")
async def chat_query(request: QueryRequest):
    """
    Stream an LLM response grounded in Weaviate creator data.
    Returns Server-Sent Events (SSE) so the frontend can stream text token by token.
    """
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in pipeline.stream_response(request.question):
                # SSE format: each event is "data: <content>\n\n"
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/rankings")
async def get_rankings():
    """
    Return the four ranking lists from Feast online store.
    Falls back to simple Weaviate queries if Feast is unavailable.
    """
    # TODO: implement Feast-backed rankings in Phase 2
    # For now return placeholder structure
    return {
        "newest_added": [],
        "cluster_highlights": [],
        "note": "Live rankings are a Phase 2 feature. See docs/rankings_phase2.md"
    }


@app.post("/api/admin/reload")
async def reload_data(
    request: ReloadRequest,
    x_admin_token: str = Header(default=""),
):
    """
    Called by Airflow after a successful training run.
    Downloads the new Parquet from Oracle Object Storage and upserts
    updated embeddings into the Weaviate index.
    """
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")

    # Run reload asynchronously so the HTTP response returns immediately
    asyncio.create_task(_reload_weaviate(request.parquet_s3_path))
    return {"status": "reload_started", "path": request.parquet_s3_path}


async def _reload_weaviate(parquet_s3_path: str):
    """Background task: download Parquet and upsert into Weaviate."""
    import tempfile
    import pandas as pd
    import boto3

    print(f"[reload] Starting Weaviate reload from {parquet_s3_path}")

    try:
        # Download Parquet
        parts = parquet_s3_path[5:].split("/", 1)
        bucket, key = parts[0], parts[1]

        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("OCI_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("OCI_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("OCI_SECRET_KEY"),
        )

        with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
            s3.download_file(bucket, key, f.name)
            df = pd.read_parquet(f.name)

        print(f"[reload] Loaded {len(df):,} creators from Parquet")

        # Upsert into Weaviate
        # (embeddings in the Parquet are the UMAP coords; the full vectors come from
        #  the embedding service at query time — see rag_pipeline.py)
        wv = pipeline._get_weaviate()
        collection = wv.collections.get("Creator")

        with collection.batch.dynamic() as batch:
            for _, row in df.iterrows():
                batch.add_object(
                    properties={
                        "creator_id": row["creator_id"],
                        "display_name": row["title"],
                        "bio_text": row.get("description", ""),
                        "cluster_id": int(row["cluster_id"]),
                        "cluster_name": row.get("cluster_name", ""),
                    }
                    # Note: pre-computed vectors are NOT in the Parquet.
                    # The embedding service computes them at query time.
                    # To store vectors here, run the embedding service at reload time.
                    # See scripts/load_weaviate.py for the full vector-loading path.
                )

        print(f"[reload] Weaviate upsert complete ({len(df):,} objects)")

    except Exception as e:
        print(f"[reload] ERROR: {e}")
