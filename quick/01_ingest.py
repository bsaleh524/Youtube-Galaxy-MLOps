"""
Step 1: load the raw Fandom JSON, embed each creator's description, and
batch-insert into Weaviate.

This is the entire "how do you build a vector DB" story:
  1. Define a schema (a "collection" in Weaviate-speak — like a table).
  2. Turn each row's text into a vector (embedding).
  3. Insert {properties, vector} pairs in batches.

Usage:
    python 01_ingest.py --limit 2000     # fast subset, good for iterating
    python 01_ingest.py                  # full 20,807 creators
    python 01_ingest.py --rebuild        # drop and recreate the collection first
"""

import argparse
import json
import time
from pathlib import Path

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from _shared import COLLECTION_NAME, EMBEDDING_MODEL, connect

DATA_PATH = Path(__file__).resolve().parents[2] / "Controversy-Early-Warning-System" / "data" / "fandom" / "youtubers_data_combined.json"


def create_schema(client: weaviate.WeaviateClient, rebuild: bool) -> None:
    if client.collections.exists(COLLECTION_NAME):
        if rebuild:
            print(f"--rebuild passed: deleting existing '{COLLECTION_NAME}' collection")
            client.collections.delete(COLLECTION_NAME)
        else:
            print(f"'{COLLECTION_NAME}' collection already exists — skipping schema creation")
            return

    client.collections.create(
        name=COLLECTION_NAME,
        # Configure.Vectorizer.none() = "I'll supply the vectors myself"
        # (the alternative is a built-in module like text2vec-transformers,
        # which embeds for you server-side — see the README for the tradeoff).
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="creator_id", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="description", data_type=DataType.TEXT),
            Property(name="youtube_url", data_type=DataType.TEXT),
        ],
    )
    print(f"Created '{COLLECTION_NAME}' collection")


def load_records(limit: int | None) -> list[dict]:
    print(f"Reading {DATA_PATH} ...")
    with open(DATA_PATH) as f:
        records = json.load(f)
    print(f"Loaded {len(records):,} creators from disk")
    if limit:
        records = records[:limit]
        print(f"Using first {len(records):,} (--limit {limit})")
    return records


def ingest(limit: int | None, rebuild: bool, batch_size: int) -> None:
    client = connect()
    try:
        create_schema(client, rebuild)
        collection = client.collections.get(COLLECTION_NAME)

        if collection.aggregate.over_all(total_count=True).total_count > 0 and not rebuild:
            print("Collection already has data — pass --rebuild to re-embed from scratch.")
            return

        records = load_records(limit)

        print(f"Loading embedding model '{EMBEDDING_MODEL}' (first run downloads it, ~90MB)...")
        model = SentenceTransformer(EMBEDDING_MODEL)

        print(f"Embedding + inserting {len(records):,} creators...")
        start = time.time()
        inserted, failed = 0, 0

        with collection.batch.dynamic() as batch:
            for record in tqdm(records):
                try:
                    # TRY THIS: this is the "what text becomes the embedding"
                    # decision — a real RAG system spends a lot of time here.
                    # Right now we embed title + truncated description. Try
                    # embedding just the title, or the full description, and
                    # see how retrieval quality in 02_search.py changes.
                    text_to_embed = f"{record['title']}. {record.get('description', '')[:1000]}"
                    vector = model.encode(text_to_embed).tolist()

                    batch.add_object(
                        properties={
                            "creator_id": record.get("id", ""),
                            "title": record.get("title", ""),
                            "description": record.get("description", "")[:2000],
                            "youtube_url": record.get("youtube_url", ""),
                        },
                        vector=vector,
                    )
                    inserted += 1
                except Exception as e:
                    failed += 1
                    print(f"  FAILED on {record.get('id')}: {e}")

        elapsed = time.time() - start
        print(f"\nDone: {inserted:,} inserted, {failed} failed, {elapsed:.1f}s "
              f"({inserted/elapsed:.1f} records/s)")

        if batch.number_errors > 0:
            print(f"Weaviate reported {batch.number_errors} batch errors — "
                  f"see collection.batch.failed_objects for details")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only ingest the first N records (for fast iteration)")
    parser.add_argument("--rebuild", action="store_true", help="Drop and recreate the collection before ingesting")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    ingest(limit=args.limit, rebuild=args.rebuild, batch_size=args.batch_size)
