"""
RAG pipeline for the Galaxy chatbot.

Flow:
  1. Detect if query names a known creator → Feast lookup for stored embedding
  2. Otherwise → embedding service for query vector
  3. Weaviate hybrid search → top K creator context
  4. Build prompt
  5. Stream LLM response (Ollama locally, Groq on Oracle Cloud)
"""

import os
from typing import AsyncGenerator

import httpx
import weaviate
import weaviate.classes.query as wq
from weaviate.classes.query import Filter, MetadataQuery

WEAVIATE_URL = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
EMBEDDING_SERVICE_URL = os.environ.get("EMBEDDING_SERVICE_URL", "http://localhost:8001")
FEAST_AVAILABLE = os.environ.get("FEAST_ENABLED", "false").lower() == "true"

LLM_BACKEND = os.environ.get("LLM_BACKEND", "groq")  # "ollama" or "groq"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral:7b-instruct-q8_0")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-70b-versatile")

SYSTEM_PROMPT = """You are a YouTube creator analyst for the Galaxy project.
You have access to a database of YouTube creators, their content clusters, and similarity relationships.
Answer questions based ONLY on the context provided. Be concise and specific.
If the answer isn't in the context, say so clearly."""

RAG_TOP_K = 8
HYBRID_ALPHA = 0.6  # 0 = pure keyword, 1 = pure vector


class RAGPipeline:
    def __init__(self):
        self._weaviate: weaviate.WeaviateClient | None = None
        self._feast_store = None

    def _get_weaviate(self) -> weaviate.WeaviateClient:
        if self._weaviate is None or not self._weaviate.is_connected():
            self._weaviate = weaviate.connect_to_local(
                host=WEAVIATE_URL.replace("http://", "").split(":")[0],
                port=int(WEAVIATE_URL.split(":")[-1]) if ":" in WEAVIATE_URL else 8080,
            )
        return self._weaviate

    def _get_feast(self):
        if not FEAST_AVAILABLE:
            return None
        if self._feast_store is None:
            from feast import FeatureStore
            features_path = os.environ.get("FEAST_REPO_PATH", "/app/features")
            self._feast_store = FeatureStore(repo_path=features_path)
        return self._feast_store

    async def _embed_query(self, text: str) -> list[float]:
        """Call the embedding microservice to get a vector for a query string."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMBEDDING_SERVICE_URL}/embed",
                json={"text": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def _retrieve_context(self, query: str, query_vector: list[float]) -> list[dict]:
        """Hybrid search: vector similarity + keyword matching."""
        wv = self._get_weaviate()
        collection = wv.collections.get("Creator")

        response = collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=HYBRID_ALPHA,
            limit=RAG_TOP_K,
            return_metadata=MetadataQuery(score=True),
            return_properties=[
                "creator_id", "display_name", "bio_text",
                "cluster_name", "subscriber_count",
            ],
        )

        return [
            {
                "name": obj.properties.get("display_name", ""),
                "cluster": obj.properties.get("cluster_name", ""),
                "bio": obj.properties.get("bio_text", "")[:400],
                "subscribers": obj.properties.get("subscriber_count", 0),
                "score": obj.metadata.score,
            }
            for obj in response.objects
        ]

    def _build_prompt(self, user_question: str, context: list[dict]) -> str:
        context_text = "\n\n".join(
            f"{i+1}. **{c['name']}** (cluster: {c['cluster']}, "
            f"~{c['subscribers']:,} subscribers)\n   {c['bio']}"
            for i, c in enumerate(context)
        )
        return f"""{SYSTEM_PROMPT}

Context — relevant YouTube creators:
{context_text}

User question: {user_question}
Answer:"""

    async def _stream_ollama(self, prompt: str) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
            ) as response:
                import json
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if chunk := data.get("message", {}).get("content", ""):
                                yield chunk
                        except json.JSONDecodeError:
                            pass

    async def _stream_groq(self, prompt: str) -> AsyncGenerator[str, None]:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=GROQ_API_KEY)
        stream = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=800,
        )
        async for chunk in stream:
            if content := chunk.choices[0].delta.content:
                yield content

    async def stream_response(self, question: str) -> AsyncGenerator[str, None]:
        """Full RAG pipeline: embed → retrieve → prompt → stream."""
        # Get query vector
        query_vector = await self._embed_query(question)

        # Retrieve context from Weaviate
        context = await self._retrieve_context(question, query_vector)

        if not context:
            yield "I couldn't find relevant creators in the database for that query."
            return

        # Build prompt
        prompt = self._build_prompt(question, context)

        # Stream from the configured LLM backend
        if LLM_BACKEND == "ollama":
            async for chunk in self._stream_ollama(prompt):
                yield chunk
        else:
            async for chunk in self._stream_groq(prompt):
                yield chunk
