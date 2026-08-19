"""Small bits shared by 01_ingest.py, 02_search.py, and 03_rag_chat.py."""

import weaviate

COLLECTION_NAME = "Creator"

# TRY THIS: swap "all-MiniLM-L6-v2" (384-dim, fast, decent quality) for a
# bigger model like "all-mpnet-base-v2" (768-dim, slower, better quality) and
# see if retrieval feels noticeably different. If you change this, re-run
# 01_ingest.py with --rebuild — queries must be embedded with the SAME model
# used at ingestion time, or the vectors aren't comparable.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def connect() -> weaviate.WeaviateClient:
    return weaviate.connect_to_local(host="localhost", port=8080, grpc_port=50051)
