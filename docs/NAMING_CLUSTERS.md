# Naming the placeholder clusters

55 of the 120 clusters have placeholder names made from keywords (like "tech · technology · educational"). This guide gives them real names. The quick way is one upload to a chat assistant. The slow way, one cluster at a time, is below it for touch-ups.

## The one-shot way (recommended)

You need a Claude Pro or Gemini Pro chat in the browser. Everything is local until you upload the file. The file holds only public wiki text and creator names.

1. **Make the brief:**

   ```bash
   make naming-brief
   ```

   This writes `data/runs/<fit run>/naming_brief.md` (now `data/runs/20261123-132613/naming_brief.md`, about 300 KB). It holds:
   - the instructions;
   - the names already taken;
   - for every unnamed cluster: its size, keywords, nearest other clusters, and the 30 creators nearest its centre, each with a line saying what they make.

   It ends by asking for one JSON object in the exact format `data/cluster_names.json` uses.
2. **Upload it to a new chat.** Attach `naming_brief.md` (or paste its contents) and send it with a short message such as "Follow the instructions in this file." The file already contains the full prompt.
3. **Save the reply.** Copy the chatbot's whole answer into a text file, e.g. `~/Desktop/names_reply.txt`. Extra words or a ```` ```json ```` fence around the JSON are fine.
4. **Check it without writing anything:**

   ```bash
   make import-names FILE=~/Desktop/names_reply.txt DRY=1
   ```

   It lists what would be added and warns about:
   - **unknown keys**, which the chatbot made up; they are skipped;
   - **empty names**, also skipped;
   - **duplicate names**, i.e. a name already used by another cluster.

   If there are duplicates, you can ask the chat to rename those keys, or fix them by hand after importing.
5. **Import for real:**

   ```bash
   make import-names FILE=~/Desktop/names_reply.txt
   ```

   This merges into `data/cluster_names.json`, creating the file if needed. Names you already set are kept. Add `FORCE=1` to let the reply replace them.
6. **Look, then publish:**

   ```bash
   make build
   make preview        # open http://localhost:8080/galaxy/ ; Ctrl+C to stop
   make publish
   ```

   To change a few names after looking, edit `data/cluster_names.json` directly (see below), then run `make build` again.

Running `make naming-brief` again only includes clusters that are still unnamed. If the chat skipped some keys, re-run the brief and upload the shorter file.

**Which chat?** Either works. The brief is about 75k tokens, inside both Claude Pro's and Gemini Pro's limits. Claude is usually stricter about "reply with only the JSON". If you want a second opinion, run the brief through both and keep the names you prefer.

## One at a time (for touch-ups)

Use this to fix a few names, or to rename any of the 65 already-named clusters (their keys are in `data/model/galaxy/registry.json`).

| File | What it is |
|---|---|
| `data/runs/20261123-132613/unnamed_clusters.md` | The list: key, size and placeholder for all 55, as of the fit. |
| `data/runs/20261123-132613/naming_packs/<key>.md` | One per cluster: the 30 creators nearest its centre, the top keywords, and a ready-made prompt for a free chatbot. |
| `data/cluster_names.json` | Your names, key → name. |

1. Look at the cluster's pack, or its section in `naming_brief.md`.
2. Add or edit its line in `data/cluster_names.json`. Each line needs a comma after it except the last:

   ```json
   {
     "c008": "Tech, Engineering & Finance",
     "c019": "Speedrunning",
     "c087": "Plants vs. Zombies"
   }
   ```

   Your names always win over the Gemini and placeholder names. Prefer the existing style: 2–5 words, "X & Y" (e.g. "Tech Reviews & Engineering").
3. Run `make build`, then `make preview` (optional), then `make publish`.

## Tips

- **Some clusters share a theme.** Several placeholders mention "blade · social". Their bios quote Social Blade subscriber stats, so the real theme is in the creator list, not the keywords. Two clusters share the placeholder "blade · social · time" (c045 and c103) and need different names.
- **Clusters with similar placeholders differ in their creators.** For example, c042, c058, c070 and c115 are all Minecraft. The brief lists each cluster's nearest neighbours so the chat can tell them apart. Check those names yourself in the preview.
- **A typo in the JSON** (missing comma or quote) makes `make build` and `make import-names` stop with an error. Fix the file and run it again.
- **Don't run `make recluster FRESH=1` after naming.** It renumbers the clusters, so your names would land on the wrong ones. Plain `make recluster` and the weekly `make pipeline` keep the keys, so your names stay put. See `docs/EMBEDDINGS.md` §7.
- `data/cluster_names.json` lives under `data/`, so it isn't in git. It's listed under "Never delete" in `docs/TO_DELETE.md`. Keep your own copy if you care about it.
