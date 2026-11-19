# Checkpoint 2: local pipeline report (2026-11-19)

Plan 2 is built: one command turns the wiki snapshot into a clustered, named, coloured map plus the chat search files, all locally and for $0. This report is for you to review before Plan 3 (the website).

**In one paragraph.** The pipeline works and is fully reproducible: running it from scratch gives byte-identical output, and a weekly run with nothing new takes about a second. You picked 120 clusters. 71 got names from your old Gemini labels; 49 need names from you. The sanity checks found one real quality problem: **neighbours and some clusters are pulled together by similar creator *names*, not just similar content** (6 of 15 checks look right, 5 half right, 4 wrong). It's the same root cause as the "Alex" cluster (issue #5), and it's wider than we thought. It doesn't block building the website, because the website reads whatever the pipeline produces, but it should be fixed before the site goes public.

---

## 1. Runtime and setup

Fresh run from scratch on the dev Mac (Apple GPU, "MPS"):

| Step | Command | Time |
|---|---|---|
| Snapshot the seed data | `make seed` | 2 s |
| Embed 20,807 creators | `make embed` | 2 min 51 s (129 creators/s) |
| Full re-cluster (k=120) | `make recluster` | 58 s |
| Build site + chat files | `make build` | 11 s |
| Weekly run (embed → assign → build), forced | `make pipeline FORCE=1` | 23 s |
| Weekly run, nothing changed | `make pipeline` | 1 s ("nothing changed") |

- **Creators truncated:** 5,319 of 20,807 (26%) have more than 2,000 characters of text, so only the first ~2,000 characters were embedded. The embedding model only reads about 512 tokens (≈ 2,000 characters) anyway, so nothing was lost by cutting there.
- **Reproducible:** the fresh run produced byte-identical files to the earlier run.

## 2. File sizes (build `20261118-171847-c390a7b8`)

| | Raw | Compressed (gzip) |
|---|---|---|
| Website files (map, neighbours, clusters, 120 detail files) | 21.5 MB | 6.1 MB |
| Chat Worker bundle (search index, centroids, snippets) | 19.8 MB | 9.7 MB |

The Worker bundle is just under the 20 MB warning line tied to issue #1 (CPU spikes). Shortening the 400-character snippets is the easy lever if needed.

## 3. What the quality score (silhouette) means

**What it measures.** For each creator, silhouette compares two distances: how close it is to the rest of its own cluster, and how close it is to the next-nearest cluster. The score runs from −1 to 1:
- near **1**: the creator sits deep inside its own cluster, far from others;
- near **0**: it sits on the border between two clusters;
- below **0**: it's closer to another cluster than its own.

The number reported is the average over 10,000 creators.

**Why text clusters score low.** YouTube topics overlap (a Minecraft animator is gaming *and* animation; a commentary channel covers everything). The embeddings also live in 384 dimensions, where distances bunch together. So text clusters typically score around 0.03–0.10, and a low number is normal, not a failure.

**Ours is 0.012**, below even that typical range. Part of that is the overlap above; part is likely the name problem in section 6. It's flat across 60, 120 and 200 clusters, so **it can't choose the cluster count for us**. That's why the choice came down to the examples below. It becomes the baseline for Plan 5's publish gate: a future run shouldn't drop much below it.

## 4. Cluster count comparison

| Clusters | Silhouette | Sizes (min / median / max) | Under 20 | Named from Gemini labels | You'd name |
|---|---|---|---|---|---|
| 60 | 0.0130 | 132 / 301.5 / 743 | 0 | 45 | 15 |
| **120 (chosen)** | **0.0120** | **43 / 173 / 440** | **0** | **71** | **49** |
| 200 | 0.0146 | 14 / 102 / 337 | 3 | 73 | 127 |

**The trade-off.** More clusters give more specific groups, names and colours, but more naming work and smaller clusters. Fewer clusters give broad, dull groups, which is what we want to avoid. Examples:
- **60** lumps things together: its "Ice Hockey (NHL)" cluster also holds the Philadelphia 76ers and Seattle Mariners.
- **200** finds real niches ("Mainstream Hip-Hop": Lil Wayne, Travis Scott, Meek Mill). But it also makes more name-based clusters ("nathan · nate · nicholas"; 14 VTubers all called Momo), and leaves 127 to name.

**Your decision:** 120 for now. The goal is many niche clusters that each make sense, so fixing issue #5 is what unlocks going higher.

Full report: `data/runs/compare-k-20261118/compare_k.md`.

### Unnamed clusters

- **k=60 (15):** animator · animations · animated; music · songs · song; series · characters · game; series · called · gaming; pokémon · nintendo · games; comedy · tiktok · vlogs; animation · animations · animator; posted · january · later; music · musician · songs; vlogs · beauty · vlogger; gaming · game · games; commentary · comedy · topics; animations · animator · animation; gaming · games · game; noxinfluencer · blade · wide.
- **k=120 (49, the live set):** music · songs · artists; commentary · matt · commentator; indonesian · gacha · japan; minecraft · hypixel · server; album · singer · musician; commentary · memes · gaming; animation · animations · blade; german · france · french; plants · zombies · pvz; noxinfluencer · blade · wide; allegations · twitter · calling; vtuber · affiliated · debuted; vtuber · affiliated · vtubers; minecraft · gaming · games; space · science · educational; vtuber · japanese · vtubers; company · founded · manufacturer; series · characters · character; rap · comedy · musician; speedruns · speedrunner · rubik; roblox · making · got; jack · english · james; episodes · episode · comedy; games · game · voice; views · channels · vlogs; games · game · gaming; alex · alexander · alexandra; noxcrew · dodgebolt · multiplier; gaming · games · game; government · organization · founded; gun · pixel · weapons; minecraft · server · survival; roblox · tower · game; beauty · vlogs · fashion; nintendo · mario · super; educational · science · university; label · music · record; band · formed · metal; books · book · witchcraft; singer · released · song; pokémon · pokemon · nuzlocke; animated · animation · series; gaming · titled · wide; games · gaming · game; animations · animator · animation; animator · animations · animated; games · game · gaming; railway · trains · train; dinosaur · dinosaurs · jurassic.
- **k=200 (127):** see `data/runs/compare-k-20261118/k200/unnamed_clusters.md`.

Naming packs (30 typical creators, keywords and a ready-to-paste Gemini prompt per cluster) are in `data/runs/20261118-171713/naming_packs/`.

## 5. Sanity checks (k=120)

For 15 well-known creators: their cluster, their 10 nearest neighbours, and a verdict. ✓ looks right · ◐ half right · ✗ wrong.

| # | Creator | Cluster | Neighbours (first few) | Verdict |
|---|---|---|---|---|
| 1 | Dream | Minecraft Survival & SMPs | Sapnap, GeorgeNotFound, TommyInnit, Logdotzip, Dream Team Gaming | ✓ His exact friend group. |
| 2 | Ninja | Fortnite & Competitive Gaming | Myth, Tfue, NICKMERCS, TimTheTatman, Symfuhny | ✓ All Fortnite streamers. |
| 3 | James Charles | Beauty & Lifestyle Influencers | Tati, Jaclyn Hill, Jeffree Star, Manny Mua, Kylie Jenner | ✓ Spot on (apart from one "James" and "JackG210"). |
| 4 | Dude Perfect | Variety Vlogs & Challenges | That's Amazing, The Try Guys, The Slow Mo Guys, Boh3m3 | ✓ Trick-shot and challenge groups. |
| 5 | CoryxKenshin | FNAF Animation & Fangames | Dawko, GoronGuy123, Spazkidin3D, KonekoKitten | ✓ Horror and FNAF gaming fits him. |
| 6 | Target / TARGET (same-title pair) | Retail & Corporate Brands / gaming · titled · wide | Target → Walmart, Costco, Shipt, Staples; TARGET → Target3DGaming, FaZe Clan | ✓ Two distinct creators kept apart, each in a sensible place. |
| 7 | Markiplier | games · gaming · game | Ethan Nestor, Jacksepticeye ✓; then LS Mark, ImMarksman, Mark SW | ◐ Real friends first, then other "Marks". |
| 8 | Linus Tech Tips | Tech Reviews & DIY | Unbox Therapy, Taran Van Hemert ✓; Linkus7, LinusStudios | ◐ Right cluster; some neighbours only share the name. |
| 9 | Technoblade | minecraft · server · survival | Mostly small Minecraft server channels; Social Blade | ◐ Right world, weak neighbours. |
| 10 | Smosh | episodes · episode · comedy | Smosh Pit, SmoshAlike, Shut Up! Cartoons ✓; SMOL, Smike | ◐ Related channels, plus "Sm…" names. |
| 11 | MrBeast | allegations · twitter · calling | Karl, Jake Paul, MrBeast Burger ✓; DogPack404, CjTheseDays | ◐ Lands in a drama cluster; half the neighbours are random. |
| 12 | PewDiePie | jack · english · james | XxDRxXCHIMP, Sive, RoomieOfficial, Durv | ✗ No real connection; sits in a name-based cluster. |
| 13 | Marques Brownlee | Tech Reviews & DIY | Brownie, M.B. Archives, BigB, Mully | ✗ Right cluster, but neighbours just share "B"/"Brown" names. |
| 14 | Vsauce | views · channels · vlogs | Vsauce2, Vsauce3 ✓; D!NG, Vinesauce, Saverino | ✗ Science-education channel among name lookalikes. |
| 15 | Kurzgesagt | Science & History Education | Whatifalthist, Casual Lectures ✓; KurashGD, KuruHS, Kurigamesalot | ✗ Right cluster, but most neighbours are "Ku…" names. |

**Score: 6 ✓, 5 ◐, 4 ✗.**

## 6. What the checks show

Clusters are mostly right (11 of 15 land in a sensible cluster), but **nearest neighbours are often chosen by name, not content**. The text we embed starts with the creator's title, then the wiki's bio opening ("Marques Keith Brownlee (born…), better known online as MKBHD…"). For big creators, whose pages are long, that opening is a large share of the ~512 tokens the model reads. So creators with similar names end up looking similar.

Chat search is much less affected: topic queries like "makeup and beauty tutorials" returned the right creators in Task 9, because a topic query doesn't contain a name.

I've added these findings to **issue #5**, widening it from "first-name clusters" to "names dominate the embedding". Likely fixes, cheapest first:
1. drop the title and strip the bio opening from the embedded text;
2. embed several chunks of the page and average them, so the long middle of the page counts too.

Each is a ~3-minute re-embed, and the 15 checks above become the before/after test.

## 7. Open issues

| # | Issue | Status |
|---|---|---|
| 1 | Chat Worker CPU spikes on 1–2% of requests | Deferred to polish |
| 2 | Wiki pages covering several channels | Deferred; one record per page |
| 3 | Where data is stored and backed up (Synology?) | Open |
| 4 | Refresh from a new Fandom dump (keep vanished creators, flagged) | Waiting on Fandom |
| 5 | **Names dominate the embeddings** (Alex cluster, neighbour lookalikes) | Deferred by you; recommended before going public |
| 6 | Automatic cluster-name suggestions | Later feature |

Files you can delete are tracked in [`docs/TO_DELETE.md`](TO_DELETE.md) (about 680 MB right now).

## 8. What I need from you

1. **Cluster count:** done. You chose 120.
2. **Names:** look over the 49 placeholder names (list above, or `data/model/galaxy/registry.json`) and the naming packs. Put any names you want in `data/cluster_names.json`, e.g. `{"c071": "Alex & Friends"}`; they take effect on the next `make build`. This can happen any time; it doesn't block Plan 3.
3. **The 0.2 match threshold** for reusing your Gemini names: matches just above it still looked right ("Spongebob Parodies & YTPs" at 0.20). Keep it, or should it be stricter?
4. **Issue #5 timing:** fix it before Plan 3, or after Plan 3 but before the site goes public? I recommend the latter, so the website work isn't blocked. The website reads whatever the pipeline produces, so nothing has to be redone.
