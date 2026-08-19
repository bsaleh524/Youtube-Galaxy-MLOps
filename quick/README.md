# quick/ — RAG + Weaviate + Claude, no k8s/Airflow/Feast

A minimal, standalone version of the full `Youtube-Galaxy-MLOps` pipeline. Same
underlying idea (creator data → vector DB → LLM chatbot) with everything that
isn't Weaviate or the LLM stripped out. Built for a fast, hands-on cram — run
each script in order, read the comments, then start tweaking.

## What you're learning

1. **How a vector DB is built** — turn text into embeddings, define a schema
   (collection), batch-insert objects with vectors attached.
2. **Vector search vs. hybrid search** — pure cosine-similarity search vs.
   blending it with BM25 keyword search (Weaviate's `alpha` parameter).
3. **RAG, end to end** — embed the user's question → retrieve top-K similar
   docs from the vector DB → stuff them into a prompt → call an LLM → stream
   the answer back. That's the entire pattern; everything else is scaffolding.
4. **Where "MLOps" would hook in** — see the `MLOps hooks` section below. This
   quick version skips all of it on purpose; the full repo (`../serving/`,
   `../dags/`, `../features/`) is where those hooks actually live.

## Setup (5 minutes)

```bash
cd quick

# 1. Python deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Start Weaviate (just the vector DB — no other services)
docker compose up -d
docker compose ps   # wait until it says "healthy"

# 3. API key
cp .env.example .env
# edit .env and paste your ANTHROPIC_API_KEY
```

## Run order

```bash
python 01_ingest.py --limit 2000     # embed + load a subset (fast — ~2-3 min)
# python 01_ingest.py                # or: the full 20,807 creators (~20-30 min on CPU)

python 02_search.py "gaming channel that does music covers"   # raw vector search, no LLM
python 03_rag_chat.py                                          # full RAG chat loop
```

`01_ingest.py` is idempotent-ish: it checks if the collection already has data
and skips re-embedding unless you pass `--rebuild`.

## Files

| File | What it teaches |
|---|---|
| `docker-compose.yml` | The only infra you need — one Weaviate container, anonymous auth, local volume |
| `01_ingest.py` | Load JSON → embed each `description` with `sentence-transformers` → batch-insert into Weaviate |
| `02_search.py` | Bare vector/hybrid search against the collection — no LLM, just to see retrieval work in isolation |
| `03_rag_chat.py` | Full RAG loop: embed query → hybrid search → build prompt → stream Claude's answer |

Each script has `# TRY THIS:` comments at the exact lines worth tweaking to
build intuition (embedding model, `alpha`, `top_k`, prompt shape).

## Concepts crib sheet (for the interview)

**What is a vector database, really?**
A regular DB indexes by exact match (`WHERE id = X`). A vector DB indexes by
*similarity* — every row also gets a dense vector (embedding), and queries are
"find me the K rows whose vectors are closest to this query vector" (usually
cosine similarity), using an approximate-nearest-neighbor index (Weaviate uses
HNSW) so it doesn't have to compare against every row.

**Why "hybrid" search?**
Pure vector search is great at *semantic* matches ("funny cat videos" finds
"comedic feline content") but bad at exact terms (a creator's exact name, a
specific game title). BM25 keyword search is the opposite. Hybrid search runs
both and blends the scores with `alpha` (0 = pure keyword, 1 = pure vector).
Most production RAG systems land around `alpha=0.5-0.75`.

**What does "RAG" actually add over just prompting the LLM?**
The LLM's training data is frozen and doesn't include your private/recent
data. RAG retrieves the *relevant slice* of your data at query time and drops
it into the prompt as context, so the model can answer using it — without
retraining or fine-tuning. The retrieval step is the only new piece; the LLM
call itself is a normal API call with a bigger prompt.

**Where does embedding happen, and why sentence-transformers here instead of
an API?**
Anthropic doesn't offer an embeddings endpoint — Claude is generation-only.
This script uses `sentence-transformers` (`all-MiniLM-L6-v2`, runs locally,
384-dim, fast) so ingestion needs zero extra API calls or keys. In production
you'd usually pick a purpose-built embedding model (Voyage AI is Anthropic's
recommended embedding partner, OpenAI's `text-embedding-3-*`, or a hosted
`sentence-transformers` model) and keep the *same* model for both ingestion
and query-time embedding — mismatched embedding models is a classic RAG bug.

**MLOps hooks this quick version deliberately skips** (see the full repo for
where they'd go):
- **Airflow** — this ingestion script is a one-shot CLI; a real pipeline would
  run it as a scheduled DAG task with retries/alerting (`../dags/`).
- **Feast** — no feature store; embeddings live only in Weaviate. A feature
  store matters when the *same* embedding needs to be reused across training
  and serving without recomputing it.
- **MLflow** — no experiment tracking. If you were comparing embedding models
  or chunking strategies, you'd log recall@K per config to MLflow.
- **Kubernetes** — everything here runs as local processes / one Docker
  container instead of scaled, restartable services.
- **Observability** — no metrics on retrieval latency, hit rate, or LLM
  token cost. In production you'd track cache hit rate (see Claude's prompt
  caching), retrieval precision, and answer latency.
