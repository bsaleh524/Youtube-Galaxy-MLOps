# Naming the placeholder clusters

55 of the 120 clusters have placeholder names made from keywords (like "tech · technology · educational"). This guide gives them real names. You don't need to do all 55 at once; every name you add shows up on the next build.

## What you need

All of this is local, in the repo folder:

| File | What it is |
|---|---|
| `data/runs/20261123-132613/unnamed_clusters.md` | The list: key, size and placeholder for all 55. |
| `data/runs/20261123-132613/naming_packs/<key>.md` | One per cluster: the 30 creators nearest its centre, with the start of each bio, the top keywords, and a ready-made prompt. |
| `data/cluster_names.json` | Your names. It doesn't exist yet; you create it. |

## Steps

1. **Open the list** at `data/runs/20261123-132613/unnamed_clusters.md` and pick a cluster, e.g. `c008 | 246 | tech · technology · educational`.
2. **Look at its pack**, `data/runs/20261123-132613/naming_packs/c008.md`. Skim the 30 creators and decide what they have in common.
   - To get a suggestion, copy the prompt at the bottom of the pack into a free chatbot. It only contains creator names and keywords from the public wiki.
   - Prefer the style of the existing names: 2–5 words, "X & Y" (e.g. "Tech Reviews & Engineering").
3. **Add the name** to `data/cluster_names.json`. Create the file the first time. The format is key → name, with a comma after each line except the last:

   ```json
   {
     "c008": "Tech, Engineering & Finance",
     "c019": "Speedrunning",
     "c087": "Plants vs. Zombies"
   }
   ```

   Your names always win over the Gemini and placeholder names. You can also rename any of the 65 already-named clusters the same way; their keys are in `data/model/galaxy/registry.json`.
4. **Check it locally** (optional). Run:

   ```bash
   make build
   make preview        # then open http://localhost:8080/galaxy/ ; Ctrl+C to stop
   ```

5. **Publish** with `make build` (if you skipped step 4), then `make publish`. It takes about a minute, and the live check at the end confirms the new version.

## Tips

- **Some clusters share a theme.** Several placeholders mention "blade · social". Their bios quote Social Blade subscriber stats, so the real theme is in the creator list, not the keywords. Two clusters share the placeholder "blade · social · time" (c045 and c103). Look at both packs and give them different names.
- **Clusters with similar placeholders differ in their creators.** For example, c042, c058, c070 and c115 are all Minecraft. Check the creators to tell them apart: servers, SMPs, animations, and so on.
- **A typo in the JSON** (missing comma or quote) makes `make build` fail with an error. Fix the file and run it again.
- **Don't run `make recluster FRESH=1` after naming.** It renumbers the clusters, so your names would land on the wrong ones. Plain `make recluster` and the weekly `make pipeline` keep the keys, so your names stay put. See `docs/EMBEDDINGS.md` §7.
- `data/cluster_names.json` lives under `data/`, so it isn't in git. It's listed under "Never delete" in `docs/TO_DELETE.md`.
