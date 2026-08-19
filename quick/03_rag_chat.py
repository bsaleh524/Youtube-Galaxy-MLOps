"""
Step 3: the full RAG loop. This is the whole pattern in ~80 lines:

    user question
        -> embed it (same model used in 01_ingest.py)
        -> hybrid search Weaviate for top-K similar creators
        -> stuff those results into the prompt as context
        -> stream Claude's answer, grounded in that context

Usage:
    python 03_rag_chat.py
    (then just type questions at the prompt; Ctrl-C to quit)
"""

import os

import anthropic
import weaviate
from weaviate.classes.query import MetadataQuery
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

from _shared import COLLECTION_NAME, EMBEDDING_MODEL, connect

load_dotenv()

# TRY THIS: fewer/more retrieved docs changes both cost (bigger prompt) and
# quality (more context, but also more chance of irrelevant noise).
TOP_K = 5
HYBRID_ALPHA = 0.6

SYSTEM_PROMPT = """You are a YouTube creator analyst.
You'll be given a set of retrieved creator profiles as context, plus a
question. Answer using ONLY the provided context. If the context doesn't
contain the answer, say so plainly instead of guessing."""


def retrieve(collection, embed_model: SentenceTransformer, question: str) -> list[dict]:
    query_vector = embed_model.encode(question).tolist()
    response = collection.query.hybrid(
        query=question,
        vector=query_vector,
        alpha=HYBRID_ALPHA,
        limit=TOP_K,
        return_metadata=MetadataQuery(score=True),
    )
    return [
        {
            "title": obj.properties["title"],
            "description": obj.properties["description"],
            "youtube_url": obj.properties["youtube_url"],
            "score": obj.metadata.score,
        }
        for obj in response.objects
    ]


def build_prompt(question: str, context: list[dict]) -> str:
    if not context:
        return f"No relevant creators were found in the database for: {question}"

    # TRY THIS: this is the "prompt engineering" part of RAG. Try numbering
    # the sources, or asking Claude to cite which creator each claim came
    # from — a small prompt change here has a big effect on answer quality.
    context_block = "\n\n".join(
        f"[{i+1}] {c['title']} (relevance={c['score']:.2f})\n{c['description'][:500]}"
        for i, c in enumerate(context)
    )
    return f"Context:\n{context_block}\n\nQuestion: {question}"


def chat():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY in .env (see .env.example)")

    client = anthropic.Anthropic(api_key=api_key)
    embed_model = SentenceTransformer(EMBEDDING_MODEL)
    weaviate_client = connect()

    try:
        collection = weaviate_client.collections.get(COLLECTION_NAME)
        print("RAG chat ready. Ask about YouTube creators (Ctrl-C to quit).\n")

        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break
            if not question:
                continue

            context = retrieve(collection, embed_model, question)
            print(f"\n[retrieved {len(context)} creators: "
                  f"{', '.join(c['title'] for c in context)}]\n")

            prompt = build_prompt(question, context)

            print("Claude: ", end="", flush=True)
            # Streaming avoids waiting for the whole response before showing
            # anything, and sidesteps SDK timeout issues on long outputs.
            with client.messages.stream(
                model="claude-sonnet-5",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
            print("\n")
    finally:
        weaviate_client.close()


if __name__ == "__main__":
    chat()
