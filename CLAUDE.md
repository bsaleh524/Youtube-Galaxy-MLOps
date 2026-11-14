# YouTube Galaxy — AI Context

> Human docs and the full architecture: [README.md](README.md). Build instructions: [docs/IMPLEMENTATION_PROMPT.md](docs/IMPLEMENTATION_PROMPT.md).

## What this is
A hobby site: an explorable 2D/3D map of ~20.8K YouTube creators (clustered by wiki-text similarity) plus a chat box that answers questions about them. Source data is the Fandom YouTube wiki (no YouTube API). Budget is **$0/month**.

## Architecture in one line
Airflow + MLflow run **locally** (scrape → embed → cluster → eval → gate → build → publish). Output is **static files on Hostinger Premium** (shared hosting, static only) plus a **free Cloudflare Worker** (Workers AI) for chat. No servers, no cloud cluster.

## Current state
The repo is **mid-migration** from an older Kubernetes/Oracle design. Code outside `archive/` may still reflect the old design until `docs/IMPLEMENTATION_PROMPT.md` has been carried out. When code and README disagree, the README describes the target.

## Hard rules
- **Do not reintroduce:** Kubernetes, k3d, Helm, Oracle Cloud, Weaviate, Redis, DuckDB, Kaggle stats, Streamlit, Feast, Terraform. They live in `archive/`. Do not delete `archive/`.
- **No paid services.** Cloudflare free plan only. If a design needs a paid plan, stop and ask.
- **Hostinger Premium is static-only.** Never plan to run Python, Node or a database there.
- **Embedding model:** `BAAI/bge-small-en-v1.5` (384-dim). Local and Worker query embeddings must be compatible: same model, same pooling (CLS), same query prefix. Verify before relying on it.
- Creators are referenced by stable id, never array position.
- Secrets live only in `.env` and Worker secrets, never in git or in browser code. `data/` is gitignored.
- Fandom text is CC BY-SA: the site must credit the wiki and link each creator's source page.
- Never put the user's name, email or personal details in a scraper User-Agent or any request to an outside service.
- Don't commit unless asked. Use `git mv` when relocating tracked files.

## Layout
`pipeline/` Python package · `dags/` Airflow DAG (thin, shells out to `pipeline/`) · `web/` static site · `worker/` Cloudflare Worker · `scrapers/fandom/` scraper · `eval/` eval questions · `data/` local artifacts · `archive/` old plan.

## Quality gate (see README)
Publish only if: silhouette ≥ a floor set from a baseline run (the old 0.40 was never validated), recall@8 on `eval/questions.yaml` has not regressed, creator count ≥ ~90% of the last publish, and two-stage search agrees with brute force within tolerance.

## Known data facts
- Seed dataset: `../Controversy-Early-Warning-System/data/fandom/youtubers_data_combined.json` — 20,807 creators, keys `id, title, description, thumbnail, youtube_url, url`. Description median ~1.2K chars, p90 ~3.7K, max ~106K.
- Cluster names to seed from: `../Controversy-Early-Warning-System/creators_labeled.json` (`group_name` per creator).
- The sibling scraper `../Controversy-Early-Warning-System/src/scrapers/fandom/my_combined.py` has a broken `from utils` line and no `--output` flag; it needs fixing and an incremental mode.
