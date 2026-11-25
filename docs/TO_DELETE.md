# Files you can delete

Local files that are safe to remove. Claude never deletes these itself; it adds them here and you delete them when you want. Everything is under `data/`, which is gitignored, so none of it is on GitHub.

**Never delete:**
- `data/model/galaxy/` and `data/model/galaxy.prev/` (the live model and the one name carry-over needs);
- `data/seed/`, `data/raw/current`, and the snapshot it names;
- `data/embeddings/`, `data/cluster_names.json`;
- the newest build in `data/artifacts/galaxy/`;
- `archive/`.

When you delete something, remove its row (or move it to *Done*) and commit.

## Pending

| Path | Size | Added | Why it's safe |
|---|---|---|---|
| `data/_before_plan2_run/` | 510 MB | 2026-11-18 | The model and embeddings from before the fresh Task 11 run. The fresh run reproduced them byte-for-byte. |
| `data/raw/snapshots/20261118-041529/` | 45 MB | 2026-11-18 | Identical copy of the seed (same sha256 `19e7a79c…`). The current snapshot is `20261118-171651`. |
| `data/raw/snapshots/20261118-171358/` | 45 MB | 2026-11-18 | Same: an accidental extra `make seed` run, identical content. |
| `data/artifacts/galaxy/20261118-155920-c390a7b8/` | 40 MB | 2026-11-18 | Build identical to the newest one (`20261118-171847-c390a7b8`). |
| `data/artifacts/galaxy/20261118-171817-c390a7b8/` | 40 MB | 2026-11-18 | Same: identical build. |
| `data/artifacts/galaxy/20261118-171847-c390a7b8/` | 40 MB | 2026-11-22 | Checkpoint 2 build; superseded by `20261122-160428-c390a7b8` (same data, plus the licence link). |
| `data/artifacts/galaxy/20261122-160428-c390a7b8/` | 40 MB | 2026-11-23 | Never published; superseded by `20261123-022138-c390a7b8` (same data, licence now "CC BY-SA 3.0"). |
| `data/runs/20261118-fit-k120/` | 0.4 MB | 2026-11-18 | First k=120 fit report; the fresh fit `data/runs/20261118-171713/` has identical names and packs. |
| `data/runs/20261118-assign-check/`, `data/runs/20261118-171835/` | <0.1 MB | 2026-11-18 | One-off weekly-mode check reports. |
| `data/experiments/issue5/fix12/`, `data/experiments/issue5/blend50/` | 64 MB | 2026-11-23 | Issue #5 experiment variants that lost to fix 1. Scores kept in the `.md` files next to them and in NOTES. |
| `data/experiments/issue5/fix1/` | 32 MB | 2026-11-23 | Byte-identical to the live `data/embeddings/` (fix 1 was adopted). |
| `data/experiments/issue5/baseline_model/` | 233 MB | 2026-11-23 | Identical copy of `data/model/galaxy.prev/` (the pre-issue-5 model). |
| `data/experiments/issue5/baseline_embeddings/` | 32 MB | 2026-11-23 | Pre-issue-5 embeddings. Only needed to go back to the old map; safe once you're happy with the new one. |
| `data/spike/` | 11 MB | 2026-11-18 | Synthetic spike index from Plan 1. Optional: regenerate any time with `uv run python -m pipeline.synthetic --out data/spike` (useful for issue #1 CPU tests). |

One command for all of the above except the optional `data/spike/`:

```bash
rm -rf data/_before_plan2_run data/raw/snapshots/20261118-041529 data/raw/snapshots/20261118-171358 \
  data/artifacts/galaxy/20261118-155920-c390a7b8 data/artifacts/galaxy/20261118-171817-c390a7b8 \
  data/artifacts/galaxy/20261118-171847-c390a7b8 data/artifacts/galaxy/20261122-160428-c390a7b8 \
  data/runs/20261118-fit-k120 data/runs/20261118-assign-check data/runs/20261118-171835 \
  data/experiments/issue5/fix12 data/experiments/issue5/blend50 data/experiments/issue5/fix1 \
  data/experiments/issue5/baseline_model data/experiments/issue5/baseline_embeddings
```

Frees about 1.1 GB.

### Plan 4 ledger (added 2026-11-24)

`.superpowers/sdd/2026-11-24-plan-4-chat-search/`: the plan's progress ledger (git-ignored). Plan 4 is done, and its rulings are recorded in the final summary and in `docs/NOTES.md`. It's a few KB.

```bash
rm -rf .superpowers/sdd/2026-11-24-plan-4-chat-search
```

### Plan 5 ledger (added 2026-11-24)

`.superpowers/sdd/2026-11-24-plan-5-eval-gate/`: the plan's progress ledger (git-ignored). Plan 5 is merged (PR #12); its rulings are in the PR summary and `docs/NOTES.md`. A few KB.

```bash
rm -rf .superpowers/sdd/2026-11-24-plan-5-eval-gate
```

## Done

_(nothing yet)_
