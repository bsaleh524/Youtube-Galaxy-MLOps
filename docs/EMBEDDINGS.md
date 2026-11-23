# How creators are embedded, and how we got here

This is the record for whoever revisits the embeddings: what the pipeline does now, what we tried, how each version scored, and how to score a new idea the same way. Last updated 2026-11-23 (issue #5, Plan 3b).

## 1. What the pipeline does now

**Model.** `BAAI/bge-small-en-v1.5`:
- an open-source model, 384 dimensions, about 130 MB;
- runs **locally** on the Mac's GPU (MPS) through sentence-transformers;
- CLS pooling, vectors normalised to length 1, no passage prefix.

No outside AI service sees creator data. The model reads at most 512 tokens (about 2,000 characters), so anything longer is ignored unless we split it.

**Text.** Each creator's bio is cleaned by `pipeline/textprep.py` → `clean_text()`, then cut to its first 2,000 characters on a word boundary:

1. **Drop disambiguation lines.** Leading sentences starting "Not to be confused with", "For other uses" or "This article is about" are removed.
2. **Drop the name lead.** Wiki bios open with a lead like "Marques Keith Brownlee (born: December 3, 1993), also known online as MKBHD, … is a video producer…". Everything before the first `is` / `was` / `are` / `were` in the first 400 characters is removed. The text then starts "is a video producer, vlogger…".
3. **Remove the creator's own names everywhere.** Name words are collected from:
   - capitalised words in that lead (real names, online names, aliases);
   - the words of the title.

   Each is removed everywhere in the bio, ignoring case, along with the full title. The following are never removed:
   - words shorter than 3 letters;
   - month names;
   - **topic words**, i.e. any word that appears in at least 5% of all bios ("Minecraft", "Roblox", "American", "Twitch", 508 words in all). This way a channel called "Minecraft Universe" keeps "Minecraft".
4. If nothing is left, the title is used instead. No creator currently hits this.

Example (Vsauce):

> Before: "Not to be confused with Vinesauce. Michael David Stevens (born: January 23, 1986 …), better known online as Vsauce, is an American educational YouTuber. Vsauce creates generally educational content…"
>
> After: "is an American educational YouTuber. creates generally educational content…"

**Caching.** Each creator's vector is cached against a hash of its exact text and the model name. A weekly run only re-embeds creators whose bio changed. A full embed takes about 2 min 40 s for 20,807 creators (about 130 per second).

**Where it lives.**

| What | Where |
|---|---|
| Text rules | `pipeline/textprep.py` |
| Embedding and caching | `pipeline/embed.py` |
| Scoring | `pipeline/sanity.py` |
| Output | `data/embeddings/embeddings.npy` + `rows.json` |

`rows.json` records `text_prep: "v2-clean-chunks"`, `max_chars: 2000` and `max_chunks: 1`.

**Options kept for future experiments** (both off by default):
- `--max-chunks N` embeds up to N pieces of 2,000 characters and averages them;
- `--first-weight W` weights the first piece against the rest.

## 2. The problem (issue #5)

At Checkpoint 2 (2026-11-19) the embedded text was `"{title} - {bio}"`, cut to 2,000 characters. Because the model reads only the start, and the start of a bio is mostly names and birth dates, **vectors encoded what creators are called more than what they make**. Examples:
- Marques Brownlee's nearest neighbours were "Brownie" and "BigB".
- Kurzgesagt's were "KurashGD" and "KuruHS".
- PewDiePie sat in a cluster named "jack · english · james".
- One whole cluster was "alex · alexander · alexandra".

## 3. How we score a version

Run `make sanity` (or `uv run python -m pipeline.sanity --embeddings DIR --out FILE.md`). It reports three things for any embeddings folder.

| Score | What it measures | Good looks like |
|---|---|---|
| **Name-lookalike rate** | Of every creator's 10 nearest neighbours, the share whose title shares a 3-letter word start with the creator's (Brownlee/Brownie, Kurzgesagt/KuruHS). Next to it, the same rate for random pairs, which is pure chance: **0.6%**. | Close to chance. Some lookalikes are real (Vsauce → Vsauce2), so it never reaches 0.6% exactly. |
| **Silhouette** (k = 120, fresh k-means) | How cleanly clusters separate, from −1 to 1. Text about YouTube overlaps a lot, so values are small. Typical text clustering: 0.03–0.10. | Higher is better. Compare versions with each other, not with 1. |
| **15 sanity checks** | The 10 nearest neighbours of 15 well-known creators (Target and TARGET counted as one check), judged by eye: ✓ looks right, ◐ half right, ✗ wrong. Creators are listed by id in `pipeline/sanity.py` → `SANITY_IDS`. | The target was 12 ✓. This is a judgement call, so the first two scores are the objective ones. |

The markdown report leaves a blank "Verdict" column for the eye check. The scores for every version below are in `data/experiments/issue5/*.md` (local only) and in `docs/NOTES.md`.

## 4. What we tried (2026-11-23)

All versions use the same model. Each variant was embedded into `data/experiments/issue5/<name>/` so the live data stayed untouched until a winner was picked.

| Version | Text embedded | Name-lookalike | Silhouette | Checks ✓ / ◐ / ✗ | Embed time |
|---|---|---|---|---|---|
| **Baseline** (Checkpoint 2) | title + bio, first 2,000 chars | 14.2% | 0.012 | 6 / 5 / 4 | 2 min 51 s |
| **Fix 1 — shipped** | cleaned bio, first 2,000 chars | **2.5%** | **0.029** | **7 / 5 / 3** | 2 min 35 s |
| Fix 1 + 2 | cleaned bio, mean of up to 8 pieces of 2,000 chars (whole page) | 2.4% | 0.024 | 6 / 5 / 4 | 3 min 45 s |
| Blend | cleaned bio, 0.5 × first piece + 0.5 × mean of the rest | 2.4% | 0.019 | ~4 / 6 / 5 | 3 min 59 s |

**What we learned**
- **Removing names is the big win.** Name lookalikes fell from 24× chance to about 4×, and clusters separate 2.4× more cleanly.
  - MKBHD's neighbours became Dave2D, Soldier Knows Best and Tekify.
  - Kurzgesagt's became Free Documentary, Extra Credits, TierZoo and What If.
- **Reading the whole page hurts topics.** Famous creators' long pages are mostly generic material: subscriber milestones, controversies, collaborations, trivia. Averaging all of it puts famous creators next to other famous creators whatever they make (Linus Tech Tips and MKBHD next to gamers). It did find friend groups and rivalries better: PewDiePie ↔ T-Series and MrBeast, Technoblade ↔ TommyInnit and Tubbo, Markiplier ↔ Jacksepticeye. Even half the weight on the rest of the page was enough to lose topics.
- **Still wrong after fix 1:** Linus Tech Tips, PewDiePie, and Vsauce (next to nursery-rhyme channels). Partly right: James Charles, CoryxKenshin, Markiplier, Smosh, MrBeast.

**Fix 1 verdicts:**
- ✓ Dream, Ninja, Dude Perfect, Target/TARGET, Technoblade, Marques Brownlee, Kurzgesagt.
- ◐ James Charles, CoryxKenshin, Markiplier, Smosh, MrBeast.
- ✗ Linus Tech Tips, PewDiePie, Vsauce.

## 5. What happened after the switch

- **Re-clustered** with `make recluster K=120 FRESH=1`.
  - `FRESH=1` names clusters again from the old Gemini labels instead of carrying names over from the old clusters, which no longer describe the same groups.
  - Result: **65 clusters named, 55 placeholders** (before: 71 / 49).
  - Placeholders are now topics ("tech · technology · educational", "speedrun · speedruns · speedrunning"); the name clusters are gone.
- **Published** 2026-11-23 as build `20261123-132733-640c47c5`.
- **Side effect for chat (Plan 4):** a chat question that names a creator ("channels like Markiplier") no longer matches by meaning, because names are no longer in the vectors. Look names up first, then search by meaning.

## 6. Ideas not yet tried

Each can be scored the same way: embed into a new `data/experiments/<name>/` folder with `--out-dir`, then run `make sanity EMB=<dir> OUT=<file>.md`.
- **Smaller weight on the rest of the page** (`--first-weight 0.8`). It might keep fix 1's topics and add some of fix 2's friend groups.
- **Keep only "content" sections of the page** (videos, series, content) and skip "Personal life", "Controversies" and "Trivia". This needs section headings, which the current snapshot doesn't keep.
- **A bigger model** (e.g. bge-base, 768 dimensions). It costs more time and a bigger chat bundle, and the Worker would have to use the same model.
- **Stricter Gemini-name matching** (the 0.2 threshold). The owner wants this stricter; it's separate from embeddings.

## 7. Watch out

- **Topic words are counted across the whole corpus.** A big data refresh (issue #4) could change which words count as topics and re-embed many creators. That's harmless, just slower.
- **Run `FRESH=1` only right after a re-embed.** It restarts cluster keys at `c001`, so names in `data/cluster_names.json` would land on the wrong clusters. After naming clusters by hand, use a plain `make recluster` (names carry over) or `make cluster`.
