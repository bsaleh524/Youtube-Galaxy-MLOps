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
| `data/runs/20261118-fit-k120/` | 0.4 MB | 2026-11-18 | First k=120 fit report; the fresh fit `data/runs/20261118-171713/` has identical names and packs. |
| `data/runs/20261118-assign-check/`, `data/runs/20261118-171835/` | <0.1 MB | 2026-11-18 | One-off weekly-mode check reports. |
| `data/spike/` | 11 MB | 2026-11-18 | Synthetic spike index from Plan 1. Optional: regenerate any time with `uv run python -m pipeline.synthetic --out data/spike` (useful for issue #1 CPU tests). |

One command for all of the above except the optional `data/spike/`:

```bash
rm -rf data/_before_plan2_run data/raw/snapshots/20261118-041529 data/raw/snapshots/20261118-171358 \
  data/artifacts/galaxy/20261118-155920-c390a7b8 data/artifacts/galaxy/20261118-171817-c390a7b8 \
  data/runs/20261118-fit-k120 data/runs/20261118-assign-check data/runs/20261118-171835
```

Frees about 680 MB.

## Done

_(nothing yet)_
