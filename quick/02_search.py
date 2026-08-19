"""
Step 2: bare retrieval — no LLM involved. Just see what the vector DB
returns for a query, so retrieval and generation are two separate mental
models before you wire them together in 03_rag_chat.py.

Usage:
    python 02_search.py "gaming channel that does music covers"
    python 02_search.py "true crime commentary" --alpha 0.2   # more keyword-weighted
    python 02_search.py "true crime commentary" --alpha 1.0   # pure vector search
"""

import argparse

import weaviate
from weaviate.classes.query import MetadataQuery
from sentence_transformers import SentenceTransformer

from _shared import COLLECTION_NAME, EMBEDDING_MODEL, connect


def search(query: str, top_k: int, alpha: float) -> None:
    model = SentenceTransformer(EMBEDDING_MODEL)
    query_vector = model.encode(query).tolist()

    client = connect()
    try:
        collection = client.collections.get(COLLECTION_NAME)

        # TRY THIS: alpha blends keyword (BM25) and vector search.
        #   alpha=0.0 -> pure keyword match (exact terms matter)
        #   alpha=1.0 -> pure vector match (meaning matters, exact words don't)
        # Run the same query at 0.0, 0.5, and 1.0 and compare the results.
        response = collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=alpha,
            limit=top_k,
            return_metadata=MetadataQuery(score=True),
        )

        print(f"\nQuery: {query!r}  (alpha={alpha}, top_k={top_k})\n")
        for i, obj in enumerate(response.objects, 1):
            p = obj.properties
            print(f"{i}. {p['title']}  (score={obj.metadata.score:.3f})")
            print(f"   {p['description'][:160]}...")
            print(f"   {p['youtube_url']}\n")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Search query, e.g. 'gaming music covers'")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--alpha", type=float, default=0.6)
    args = parser.parse_args()

    search(args.query, args.top_k, args.alpha)
