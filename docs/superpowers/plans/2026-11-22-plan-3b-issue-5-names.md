# Plan 3b — Issue #5: Stop Names Dominating the Embeddings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each creator's vector describe *what they make*, not *what they're called*. Do this by stripping names from the embedded text (fix 1) and averaging over chunks of the whole page (fix 2). Then prove the result with a repeatable score and stop for the owner before publishing.

**Architecture:** All work stays in the local pipeline.
- `pipeline/textprep.py` gains name cleaning and chunking.
- `pipeline/embed.py` encodes every chunk with the same local bge-small model, then averages the chunks per creator.
- A new `pipeline/sanity.py` scores any embeddings folder: the 15 named checks, a whole-map "name lookalike" rate, and silhouette at k=120.
- Variants are embedded into `data/experiments/issue5/` first, so the live `data/embeddings/` changes only once the winner is clear.
- The website and Worker formats don't change.

**Tech Stack:** Python 3.11, uv, numpy, scikit-learn, sentence-transformers (`BAAI/bge-small-en-v1.5`, local MPS), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-15-youtube-galaxy-design.md`. The problem statement and the before-numbers are `docs/CHECKPOINT_2.md` sections 5–6 and GitHub issue #5.

## Owner decisions (2026-11-22)

- Do **both** fix 1 and fix 2. Score fix 1 alone on the way so we can see what each adds.
- Everything runs locally; no Claude/Gemini/outside model touches creator data.
- Placeholder cluster names get redone anyway (Checkpoint 2), so a fresh naming pass after the re-cluster is fine.
- Autocomplete idea: the search box already shows a live dropdown. Any improvements go in a later issue, not this plan.

## Global Constraints

- $0, no paid services. Embedding is local only.
- Commit **and push** after every task, to `superpowers-rework`. Stage specific paths. Never stage `data/` or `.env`. Never push to `main`.
- **Key everything on id, never title.** The sanity creators are listed by id.
- Don't delete anything under `data/`. Superseded folders go in `docs/TO_DELETE.md`.
- **No publish without the owner's explicit go.** This plan ends at a checkpoint report.
- **Unchanged:**
  - the embedding model, its normalisation, and "no passage prefix";
  - `index_format.py`, the Worker formats and the parity fixture.

## Review Focus

1. A creator whose cleaned text is empty (no bio, or the bio was all name) must still get a vector. Fall back to the title rather than embedding "".
2. A creator named after a topic ("Minecraft Universe", "Roblox News") must keep that topic word. Words in ≥ 5 % of all bios are protected from name removal.
3. Very long pages (up to 106k chars) are capped at `max_chunks`, and the "truncated" count still reports them.
4. The embed cache stays correct. A second run with nothing changed encodes nothing, and a changed bio re-encodes all of that creator's chunks.
5. The re-cluster must name clusters fresh from the Gemini seed labels. Carrying over the old names by centroid similarity would bring back name-based placeholder names such as "jack · english · james".

---

### Task 1: Name cleaning and chunking in `textprep`

**Files:**
- Modify: `pipeline/textprep.py`
- Modify: `pipeline/cluster.py:262-268`, `pipeline/compare_k.py:107-118` (keyword texts)
- Test: `tests/test_textprep.py` (new). Move the four existing textprep tests out of `tests/test_embed.py` and adapt them.

**Interfaces:**
- Produces:
  - `PROTECT_DF = 0.05`
  - `DEFAULT_MAX_CHARS = 2000`
  - `DEFAULT_MAX_CHUNKS = 8`
  - `TEXT_PREP = "v2-clean-chunks"`
  - `protected_words(records: list[dict], min_df: float = PROTECT_DF) -> frozenset[str]`: case-sensitive word tokens that appear in at least `min_df` of all descriptions.
  - `clean_text(rec: dict, protected: frozenset[str]) -> str`
  - `chunk_text(text: str, max_chars: int, max_chunks: int) -> tuple[list[str], bool]`: returns (chunks, truncated).
  - `embed_chunks(rec, protected, max_chars=DEFAULT_MAX_CHARS, max_chunks=DEFAULT_MAX_CHUNKS) -> tuple[list[str], bool]`
  - `keyword_text(rec, protected, max_chars=DEFAULT_MAX_CHARS) -> str`: the first chunk.
  - `text_hash(chunks: list[str], model_name: str) -> str`: sha256 of `model_name + "\0" + "\x1e".join(chunks)`.
  - `embed_text` is removed.

**`clean_text` rules, in order:**
1. Description `None` becomes `""`. Drop leading sentences that start with "Not to be confused with", "For other uses" or "This article is about". The sentence runs up to and including the first `.`.
2. **Lead.** Look for the first whole word `is|was|are|were` in the first 400 chars. If found, the lead is everything before it, and the text keeps everything from that verb on ("is an American educational YouTuber…"). If none is found, there's no lead and the text is kept whole.
3. **Name terms.** Collect:
   - every word in the lead that contains an uppercase letter;
   - every word of the title.

   A word here is a run of letters, digits, `'` or `’`. Drop terms shorter than 3 characters, English month names and anything in `protected`.
4. Remove the full title phrase, then each name term, as whole words, case-insensitively. Collapse whitespace and strip.
5. If the result is empty, return the title.

- [ ] **Step 1: Write the failing tests** in `tests/test_textprep.py`:

```python
PROTECTED = frozenset({"American", "Minecraft", "YouTuber"})

def test_lead_and_names_removed():
    rec = {"title": "Vsauce", "description": "Not to be confused with Vinesauce. Michael David Stevens "
           "(born: January 23, 1986), better known online as Vsauce, is an American educational YouTuber. "
           "Vsauce creates educational content. Michael hosts Mind Field."}
    out = clean_text(rec, PROTECTED)
    assert out.startswith("is an American educational YouTuber.")
    for name in ("Vsauce", "Michael", "Stevens", "Vinesauce", "January"):
        assert name not in out
    assert "creates educational content" in out and "Mind Field" in out

def test_protected_topic_words_survive():
    rec = {"title": "Minecraft Universe", "description": "Minecraft Universe is a channel about Minecraft maps."}
    assert clean_text(rec, PROTECTED) == "is a channel about Minecraft maps."

def test_no_lead_verb_keeps_text_but_drops_title():
    rec = {"title": "Bob", "description": "Bob uploads cooking videos weekly"}
    assert clean_text(rec, PROTECTED) == "uploads cooking videos weekly"

def test_empty_after_cleaning_falls_back_to_title():
    assert clean_text({"title": "Zed", "description": None}, PROTECTED) == "Zed"
    assert clean_text({"title": "Zed", "description": "Zed"}, PROTECTED) == "Zed"

def test_protected_words_threshold():
    recs = [{"description": "Minecraft fun"}] * 3 + [{"description": "Alex plays"}] * 1 + [{"description": None}] * 6
    assert protected_words(recs, min_df=0.2) == frozenset({"Minecraft", "fun"})

def test_chunking_word_boundaries_and_cap():
    chunks, cut = chunk_text("aa bb cc dd ee", max_chars=5, max_chunks=2)
    assert (chunks, cut) == (["aa bb", "cc dd"], True)
    assert chunk_text("aa bb", 5, 8) == (["aa bb"], False)
    chunks, cut = chunk_text("x" * 12, max_chars=5, max_chunks=8)  # no space: hard cuts
    assert chunks == ["xxxxx", "xxxxx", "xx"] and not cut

def test_text_hash_depends_on_every_chunk_and_model():
    assert text_hash(["a", "b"], "m") != text_hash(["a", "c"], "m") != text_hash(["a", "b"], "n")
    assert text_hash(["ab"], "m") != text_hash(["a", "b"], "m")
```

Keep the moved word-boundary and hard-cut cases, rewritten against `chunk_text`.

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest tests/test_textprep.py -q`
Expected: ImportError (`clean_text` not defined).

- [ ] **Step 3: Implement** the interfaces above.
  - `chunk_text` reuses the current word-boundary cut: back off to the last space unless that loses more than half the chunk. It strips each chunk and drops empty ones.
  - Update `cluster.py` and `compare_k.py` to build keyword texts with `protected = protected_words(all snapshot records)` and `keyword_text(records[rid], protected, rows["max_chars"])`.

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q && uv run ruff check pipeline tests`
Expected: the whole suite passes (test_embed.py will fail until Task 2 if it still imports `embed_text`, so do the Task 2 import change here). Ruff is clean.

- [ ] **Step 5: Commit and push**

```bash
git add pipeline/textprep.py pipeline/cluster.py pipeline/compare_k.py tests/test_textprep.py tests/test_embed.py
git commit -m "feat(textprep): strip creator names and chunk whole pages for embedding (issue #5)"
git push
```

### Task 2: Chunk-averaged embedding

**Files:**
- Modify: `pipeline/embed.py`
- Test: `tests/test_embed.py`

**Interfaces:**
- Consumes: Task 1's `protected_words`, `embed_chunks`, `text_hash`, `DEFAULT_MAX_CHUNKS` and `TEXT_PREP`.
- Produces:
  - `run(encoder, records, out_dir, model_name, max_chars=2000, max_chunks=8, snapshot_sha256=None, batch_size=256) -> dict`
    - computes `protected` once from `records`;
    - encodes all chunks of the creators to do, in flat batches;
    - each creator's vector is the mean of its chunk vectors, re-normalised to unit length.
  - `rows.json` gains `max_chunks` and `text_prep`.
  - Stats gain `"chunks"`, the number of chunks encoded.
  - CLI gains `--max-chunks N` (default 8) and `--out-dir DIR` (default `data/embeddings`).

- [ ] **Step 1: Write the failing tests**

```python
def test_vector_is_normalised_mean_of_chunks(tmp_path):
    enc = FakeEncoder()
    rec = {"id": "fandom_1", "title": "T", "description": "is " + "word " * 1200}  # ~6000 chars -> 3 chunks
    run(enc, [rec], tmp_path, MODEL, max_chars=2000, max_chunks=8)
    X, _, meta = load_embeddings(tmp_path)
    expect = enc.encode(enc.seen[:3]).mean(axis=0)
    assert len(enc.seen) == 6  # 3 chunks seen by run, 3 re-encoded just above
    np.testing.assert_allclose(X[0], expect / np.linalg.norm(expect), atol=1e-6)
    assert meta["max_chunks"] == 8 and meta["text_prep"] == "v2-clean-chunks"

def test_max_chunks_one_is_fix1_only(tmp_path):
    enc = FakeEncoder()
    run(enc, [{"id": "fandom_1", "title": "T", "description": "is " + "word " * 1200}], tmp_path, MODEL, max_chunks=1)
    assert len(enc.seen) == 1

def test_second_run_encodes_nothing_and_changed_bio_reencodes_all_its_chunks(tmp_path):
    ...  # run twice with FakeEncoder: second stats["encoded"] == 0 and stats["chunks"] == 0;
         # then change one description: stats["encoded"] == 1, chunks == that creator's chunk count
```

Update the existing run tests for the new text, using `embed_chunks` in place of `embed_text` where they compute expected hashes.

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest tests/test_embed.py -q`
Expected: FAIL (`max_chunks` unexpected keyword / no `text_prep`).

- [ ] **Step 3: Implement** `run` and the CLI flags as in Interfaces. Keep the `NORM_TOLERANCE` check on chunk vectors.

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q && uv run ruff check pipeline tests`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit and push**

```bash
git add pipeline/embed.py tests/test_embed.py
git commit -m "feat(embed): average chunk vectors per creator; --max-chunks, --out-dir (issue #5)"
git push
```

### Task 3: `pipeline.sanity`, a repeatable quality score

**Files:**
- Create: `pipeline/sanity.py`
- Modify: `Makefile` (add `sanity:` with help text "score embeddings: 15 checks, name-lookalike rate, silhouette (EMB=dir)")
- Test: `tests/test_sanity.py`

**Interfaces:**
- Consumes: `pipeline.embed.load_embeddings`, `clusterlib.top_neighbors`, `clusterlib.fit_kmeans`, `clusterlib.silhouette_cosine`, `snapshot.load_current`.
- Produces:
  - `SANITY_IDS`: the 16 ids of the Checkpoint 2 checks, in its order (Dream fandom_225303, Ninja fandom_143804, James Charles fandom_135613, Dude Perfect fandom_125499, CoryxKenshin fandom_102432, Target fandom_372805, TARGET fandom_449281, Markiplier fandom_20660, Linus Tech Tips fandom_179221, Technoblade fandom_137746, Smosh fandom_1754, MrBeast fandom_111268, PewDiePie fandom_131817, Marques Brownlee fandom_34528, Vsauce fandom_15700, Kurzgesagt fandom_120119).
  - `fold_words(title: str) -> list[str]`: NFKD, accents stripped, lowercase, split on non-alphanumerics, words of length ≥ 3.
  - `lookalike(a: str, b: str) -> bool`: true if some word of each shares its first 3 characters.
  - `lookalike_rate(titles: list[str], nbrs: np.ndarray) -> float`: share of all (creator, neighbour) pairs that are lookalikes.
  - `chance_rate(titles, n_pairs=200_000, seed=42) -> float`: the same for random pairs.
  - `score(X, ids, titles, k=120) -> dict`, with keys `lookalike_rate`, `chance_rate`, `silhouette` and `checks` (`{id: {"title", "neighbours": [10 titles]}}`).
  - CLI: `python -m pipeline.sanity [--embeddings DIR] [--out FILE.md] [--k 120]`. It writes a markdown report and prints a JSON summary line.

- [ ] **Step 1: Write the failing tests**

```python
def test_lookalike_examples():
    assert lookalike("Marques Brownlee", "Brownie")
    assert lookalike("Kurzgesagt – In a Nutshell", "KuruHS")
    assert lookalike("Markiplier", "LS Mark")
    assert not lookalike("Dream", "Sapnap")
    assert not lookalike("Ed", "Ed")  # words under 3 chars ignored

def test_rate_counts_pairs():
    titles = ["Alex A", "Alexa", "Zed"]
    nbrs = np.array([[1, 2], [0, 2], [0, 1]])
    assert lookalike_rate(titles, nbrs) == pytest.approx(2 / 6)

def test_score_shape_on_small_matrix():
    ...  # 30 random unit vectors, ids incl. one SANITY_ID, k=3: keys present, checks only for ids that exist
```

- [ ] **Step 2: Run, expect FAIL.** Run: `uv run pytest tests/test_sanity.py -q`. Expected: ImportError.
- [ ] **Step 3: Implement.** Skip any `SANITY_IDS` entry that isn't in `ids`; don't raise.
- [ ] **Step 4: Run, expect PASS.** Run: `uv run pytest -q && uv run ruff check pipeline tests`.
- [ ] **Step 5: Baseline on the live embeddings.**

Run: `uv run python -m pipeline.sanity --out data/experiments/issue5/baseline.md`
Expected: a JSON line with a silhouette close to the Checkpoint 2 value (0.012, with a different k-means seed path allowed ±0.003). The neighbours of Marques Brownlee should include Brownie/BigB, which confirms the baseline reproduces the problem.

- [ ] **Step 6: Commit and push**

```bash
git add pipeline/sanity.py tests/test_sanity.py Makefile
git commit -m "feat(sanity): repeatable embedding score: 15 checks, name-lookalike rate, silhouette"
git push
```

### Task 4: Experiments: fix 1 alone, then fix 1 + 2

No code. Live `data/embeddings/` is not touched.

- [ ] **Step 1: Embed both variants**

```bash
uv run python -m pipeline.embed --max-chunks 1 --out-dir data/experiments/issue5/fix1
uv run python -m pipeline.embed --max-chunks 8 --out-dir data/experiments/issue5/fix12
```

Expected:
- fix1 encodes 20,807 creators, 20,807 chunks, in about 3 minutes;
- fix12 encodes about 30,000 chunks in about 4–6 minutes.

Record the times.

- [ ] **Step 2: Score both**

```bash
uv run python -m pipeline.sanity --embeddings data/experiments/issue5/fix1 --out data/experiments/issue5/fix1.md
uv run python -m pipeline.sanity --embeddings data/experiments/issue5/fix12 --out data/experiments/issue5/fix12.md
```

- [ ] **Step 3: Judge the 15 checks for each variant** (✓/◐/✗, same standard as Checkpoint 2).

Write a comparison table to `docs/NOTES.md` covering baseline / fix1 / fix12:
- ✓ ◐ ✗ counts;
- lookalike rate vs chance rate;
- silhouette;
- embed time.

Also add 3–4 before/after neighbour examples.

- [ ] **Step 4: Pick the winner.**
  - **Expected:** fix12 meets ≥ 12 ✓, a lookalike rate well below baseline, and a silhouette no lower than about 0.010.
  - **If fix 2 makes things worse than fix 1 alone:** ledger a ruling and adopt fix1 (`--max-chunks 1` becomes the default).
  - **If neither variant reaches 12 ✓:** stop and report to the owner with the numbers. Don't adopt.

- [ ] **Step 5: Commit and push** the NOTES entry: `git add docs/NOTES.md && git commit -m "docs: issue #5 experiment results" && git push`.

### Task 5: Adopt, re-cluster with fresh names, build, checkpoint

**Files:**
- Modify: `pipeline/cluster.py`. Add a `--fresh-names` flag for fit mode. With it, `name_model` is called with `prev=None`, so names bootstrap from the Gemini seed labels and colours are assigned fresh. The layout still aligns to the old model with Procrustes.
- Test: `tests/test_cluster_fit.py`
- Modify: `docs/NOTES.md`, `docs/TO_DELETE.md`, `README.md` (embed flags and `make sanity` one-liner)

- [ ] **Step 1: Failing test.** Fit a model with a `prev` model whose registry holds a key named "old name". With `fresh_names=True`, no cluster carries "old name" and the keys restart at `c001`. Run it and expect FAIL.
- [ ] **Step 2: Implement `--fresh-names`.** Run `uv run pytest -q && uv run ruff check pipeline tests` and expect PASS. Then commit and push: `feat(cluster): --fresh-names to re-bootstrap names after a re-embed`.
- [ ] **Step 3: Adopt the winner on the live data.**
  - Before running: copy, don't move, `data/embeddings/` to `data/experiments/issue5/baseline_embeddings/` and `data/model/galaxy/` to `data/experiments/issue5/baseline_model/`.
  - Then run:

```bash
uv run python -m pipeline.embed            # defaults now = the winner
uv run python -m pipeline.cluster --mode fit --k 120 --fresh-names
uv run python -m pipeline.build_artifacts
uv run python -m pipeline.sanity --out data/experiments/issue5/live.md
```

Expected:
- the embed sha256 differs from `c390a7b8`;
- the fit report shows how many clusters got Gemini names and how many are placeholders;
- the build succeeds, and the Worker bundle stays under 20 MB;
- the live sanity matches the winner's numbers.

- [ ] **Step 4: Look at it.** Run `make web-build && make preview` and take a screenshot of the map and of Marques Brownlee's detail panel. Check that the 2D layout still looks like a galaxy, not one blob.
- [ ] **Step 5: Record and stop.**
  - `docs/NOTES.md`: adoption numbers and the new placeholder count.
  - `docs/TO_DELETE.md`: rows for `data/experiments/issue5/` and the now-superseded old builds.
  - Commit and push: `docs: issue #5 adopted locally (checkpoint 3b)`.
  - Report to the owner:
    - before/after table and examples;
    - placeholder count;
    - the publish command, waiting for their go.
  - Close issue #5 only after they agree.
