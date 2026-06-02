"""
Bulk-load creator data (with full GTE-Large vectors) into Weaviate.

Run this ONCE after setting up the Weaviate instance, or after a full retrain
when you want to rebuild the index from scratch.

Usage:
    python scripts/load_weaviate.py \
        --parquet-path data/starmap_data.parquet \
        --weaviate-url http://localhost:8081 \
        --embedding-service-url http://localhost:8001

For large datasets, this script batches requests to avoid OOM.
"""

import argparse
import time

import pandas as pd
import requests
import weaviate
from weaviate.classes.config import Configure, DataType, Property


def create_schema(client: weaviate.WeaviateClient):
    """Create the Creator collection if it doesn't exist."""
    if client.collections.exists("Creator"):
        print("Creator collection already exists — skipping schema creation")
        print("  To rebuild from scratch: delete it with client.collections.delete('Creator')")
        return

    client.collections.create(
        name="Creator",
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="creator_id",    data_type=DataType.TEXT),
            Property(name="display_name",  data_type=DataType.TEXT),
            Property(name="bio_text",      data_type=DataType.TEXT),
            Property(name="cluster_id",    data_type=DataType.INT),
            Property(name="cluster_name",  data_type=DataType.TEXT),
        ],
    )
    print("Creator collection created")


def embed_text(text: str, embedding_service_url: str) -> list[float]:
    """Call the embedding microservice to get a vector."""
    resp = requests.post(f"{embedding_service_url}/embed", json={"text": text}, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]


def load(parquet_path: str, weaviate_url: str, embedding_service_url: str, batch_size: int = 50):
    df = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df):,} creators from {parquet_path}")

    client = weaviate.connect_to_local(
        host=weaviate_url.replace("http://", "").split(":")[0],
        port=int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 8080,
    )

    create_schema(client)
    collection = client.collections.get("Creator")

    inserted = 0
    failed = 0
    start = time.time()

    with collection.batch.dynamic() as batch:
        for i, row in df.iterrows():
            try:
                # Build text for embedding: same format as training
                text = f"{row['title']} - {str(row.get('description', ''))[:3000]}"
                vector = embed_text(text, embedding_service_url)

                batch.add_object(
                    properties={
                        "creator_id":   row["creator_id"],
                        "display_name": row["title"],
                        "bio_text":     str(row.get("description", ""))[:500],
                        "cluster_id":   int(row["cluster_id"]),
                        "cluster_name": str(row.get("cluster_name", "")),
                    },
                    vector=vector,
                )
                inserted += 1

                if inserted % 100 == 0:
                    elapsed = time.time() - start
                    rate = inserted / elapsed
                    remaining = (len(df) - inserted) / rate
                    print(f"  {inserted:,}/{len(df):,} inserted "
                          f"({rate:.1f}/s, ~{remaining/60:.1f} min remaining)")

            except Exception as e:
                failed += 1
                print(f"  FAILED creator {row.get('creator_id', i)}: {e}")

    print(f"\nDone: {inserted:,} inserted, {failed} failed in {(time.time()-start)/60:.1f} min")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet-path", required=True)
    parser.add_argument("--weaviate-url", default="http://localhost:8081")
    parser.add_argument("--embedding-service-url", default="http://localhost:8001")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    load(args.parquet_path, args.weaviate_url, args.embedding_service_url, args.batch_size)
