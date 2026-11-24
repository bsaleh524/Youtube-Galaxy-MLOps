"""One-shot cluster naming with a chat assistant (Gemini, Claude or any other).

    make naming-brief                 # writes data/runs/<fit run>/naming_brief.md
    (upload that file to a chat, paste its reply into a text file)
    make import-names FILE=reply.txt  # checks the reply and merges it into data/cluster_names.json

The brief holds the instructions, the names already taken, and every unnamed cluster with the
creators nearest its centre. Creator snippets come from the cleaned bio (pipeline.textprep), so
they say what a creator makes rather than their birth name. Nothing here calls an LLM.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from pipeline.textprep import clean_text

PER_CLUSTER = 30
NEIGHBOURS = 3
SNIPPET_CHARS = 160


# ---- which clusters need names -------------------------------------------------------------


def unnamed_keys(keys: list[str], registry: dict, owner: dict) -> list[str]:
    """Active clusters still on a placeholder name that the owner hasn't named."""
    return [
        k for k in keys if registry["clusters"][k]["source"] == "placeholder" and k not in owner
    ]


def current_names(keys: list[str], registry: dict, owner: dict) -> dict[str, str]:
    """Real names of active clusters (owner names win); placeholders are left out."""
    out = {}
    for k in keys:
        if k in owner:
            out[k] = owner[k]
        elif registry["clusters"][k]["source"] != "placeholder":
            out[k] = registry["clusters"][k]["name"]
    return out


# ---- the brief -----------------------------------------------------------------------------


def _snippet(rec: dict, protected: frozenset[str]) -> str:
    """The start of the cleaned bio, up to SNIPPET_CHARS, cut on a word boundary."""
    text = clean_text(rec, protected)
    if len(text) <= SNIPPET_CHARS:
        return text
    cut = text[: SNIPPET_CHARS - 1]
    if not text[SNIPPET_CHARS - 1].isspace() and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"


def build_brief(
    keys: list[str],
    registry: dict,
    owner: dict,
    labels: np.ndarray,
    X: np.ndarray,
    centroids: np.ndarray,
    ids: list[str],
    records: dict[str, dict],
    protected: frozenset[str],
    per_cluster: int = PER_CLUSTER,
    neighbours: int = NEIGHBOURS,
) -> str:
    """The whole brief as markdown: instructions, taken names, one section per unnamed cluster."""
    todo = unnamed_keys(keys, registry, owner)
    named = current_names(keys, registry, owner)
    if not todo:
        return "# Cluster naming brief\n\nNothing to name: every cluster has a real name.\n"
    label_of = {k: i for i, k in enumerate(keys)}
    taken = "\n".join(f"- {n}" for n in sorted(set(named.values()), key=str.lower))
    template = "{\n" + ",\n".join(f'  "{k}": "…"' for k in todo) + "\n}"

    def label(k: str) -> str:
        return named.get(k) or f"unnamed, keywords {registry['clusters'][k]['name']}"

    lines = [
        "# Cluster naming brief",
        "",
        f"You are naming {len(todo)} groups of YouTube creators for an interactive map. Each group was",
        "formed automatically from the creators' Fandom wiki bios (with the creators' own names removed),",
        "so a group shares a topic, genre or format.",
        "",
        "## Rules",
        "",
        "1. Give every group below one name of 2-5 words, in the style of the existing names, e.g.",
        '   "Tech Reviews & Engineering" or "Cooking & Street Food". Use "&" to join two themes.',
        "2. Judge each group by its creators, not its keywords. The keywords are word counts and can",
        '   mislead: "blade · social" only means the bios quote Social Blade subscriber stats.',
        "3. Every name must be different from every other name you give and from the taken names below.",
        "   Groups that look alike (several Minecraft groups, say) need names that say how they differ:",
        "   compare their creators and the listed nearest groups.",
        "4. If a group is a mix, name what most of its creators have in common, in broad terms.",
        f"5. Reply with ONLY one JSON object with all {len(todo)} keys, exactly once each, and no other text:",
        "",
        "```json",
        template,
        "```",
        "",
        "## Names already taken",
        "",
        taken or "(none)",
        "",
        "## Groups to name",
        "",
    ]
    for k in todo:
        i = label_of[k]
        e = registry["clusters"][k]
        members = np.flatnonzero(labels == i)
        order = members[np.argsort(-(X[members] @ centroids[i]), kind="stable")][:per_cluster]
        sims = centroids @ centroids[i]
        sims[i] = -np.inf
        near = [keys[j] for j in np.argsort(-sims, kind="stable")[:neighbours]]
        lines += [
            f"### {k}",
            "",
            f"{e['size']} creators. Keywords: {', '.join(e['keywords'])}.",
            "",
            "Nearest other groups: " + "; ".join(f"{n} ({label(n)})" for n in near) + ".",
            "",
            "Creators nearest the centre:",
            "",
            *(
                f"- **{records[ids[r]]['title']}**: {_snippet(records[ids[r]], protected)}"
                for r in order
            ),
            "",
        ]
    lines += [
        "## Reminder",
        "",
        f"Reply with only the JSON object: all {len(todo)} keys ({todo[0]} … {todo[-1]}), unique names, no other text.",
        "",
    ]
    return "\n".join(lines)


# ---- reading the chat reply ----------------------------------------------------------------


def parse_reply(text: str) -> dict:
    """The JSON object in a chat reply, ignoring prose, code fences and trailing commas."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found in the reply")
    body = re.sub(r",(\s*[}\]])", r"\1", text[start : end + 1])
    try:
        data = json.loads(body)
    except json.JSONDecodeError as err:
        raise ValueError(f"the reply's JSON doesn't parse: {err}") from None
    if not isinstance(data, dict):
        raise ValueError("the reply's JSON is not an object of key -> name")  # noqa: TRY004
    return data


# ---- merging into cluster_names.json -------------------------------------------------------


def merge_names(
    existing: dict, reply: dict, keys: list[str], registry: dict, force: bool = False
) -> tuple[dict, dict]:
    """(merged names, report). Existing names stay unless force; bad entries are skipped."""
    active = set(keys)
    merged = dict(existing)
    rep = {"added": [], "replaced": [], "kept": [], "unknown": [], "invalid": [], "duplicates": {}}
    for k in sorted(reply):
        v = reply[k]
        if k not in active:
            rep["unknown"].append(k)
            continue
        if not isinstance(v, str) or not v.strip():
            rep["invalid"].append(k)
            continue
        v = " ".join(v.split())
        if k not in merged:
            merged[k] = v
            rep["added"].append(k)
        elif merged[k] != v:
            if force:
                merged[k] = v
                rep["replaced"].append(k)
            else:
                rep["kept"].append(k)
    groups: dict[str, list[str]] = {}
    spelling: dict[str, str] = {}
    for k, n in current_names(keys, registry, merged).items():
        spelling.setdefault(n.lower(), n)
        groups.setdefault(n.lower(), []).append(k)
    rep["duplicates"] = {spelling[n]: ks for n, ks in groups.items() if len(ks) > 1}
    return merged, rep


def import_reply(
    reply_text: str,
    names_file: Path,
    keys: list[str],
    registry: dict,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Parse a chat reply and merge it into names_file. Returns the merge report."""
    names_file = Path(names_file)
    existing = {}
    if names_file.exists():
        try:
            existing = json.loads(names_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise ValueError(f"{names_file.name} doesn't parse ({err}); fix it first") from None
    merged, rep = merge_names(existing, parse_reply(reply_text), keys, registry, force)
    if not dry_run and merged != existing:
        tmp = names_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(dict(sorted(merged.items())), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(names_file)
    return rep


def format_report(rep: dict) -> str:
    lines = [f"Added {len(rep['added'])}: {', '.join(rep['added']) or '-'}"]
    if rep["replaced"]:
        lines.append(f"Replaced {len(rep['replaced'])}: {', '.join(rep['replaced'])}")
    if rep["kept"]:
        lines.append(
            f"Kept your existing name for {', '.join(rep['kept'])} (FORCE=1 to take the reply's)"
        )
    if rep["unknown"]:
        lines.append(f"Skipped unknown or retired keys: {', '.join(rep['unknown'])}")
    if rep["invalid"]:
        lines.append(f"Skipped empty or non-text names: {', '.join(rep['invalid'])}")
    for name, ks in rep["duplicates"].items():
        lines.append(
            f'WARNING: "{name}" is used by {", ".join(ks)}; edit data/cluster_names.json to tell them apart'
        )
    return "\n".join(lines)


# ---- CLI -----------------------------------------------------------------------------------


def _model_parts(model_dir: Path) -> tuple[dict, dict]:
    """model.json and registry.json, without loading the 240 MB UMAP pickles."""
    meta = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
    registry = json.loads((model_dir / "registry.json").read_text(encoding="utf-8"))
    return meta, registry


def _owner(names_file: Path) -> dict:
    return json.loads(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief", help="write the naming brief for a chat assistant")
    b.add_argument("--out", type=Path, help="default: data/runs/<fit run>/naming_brief.md")
    i = sub.add_parser("import", help="merge a chat reply into data/cluster_names.json")
    i.add_argument("file", type=Path, help="text file holding the chat reply")
    i.add_argument("--force", action="store_true", help="replace names you already set")
    i.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    a = ap.parse_args(argv)

    from pipeline.config import load_settings

    settings = load_settings()
    model_dir = settings.data_dir / "model" / "galaxy"
    names_file = settings.data_dir / "cluster_names.json"
    meta, registry = _model_parts(model_dir)
    keys = meta["cluster_keys"]
    try:
        owner = _owner(names_file)
    except json.JSONDecodeError as err:
        ap.error(f"{names_file} doesn't parse ({err}); fix it first")

    if a.cmd == "import":
        try:
            rep = import_reply(
                a.file.read_text(encoding="utf-8"), names_file, keys, registry, a.force, a.dry_run
            )
        except ValueError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 1
        print(format_report(rep))
        if a.dry_run:
            print("Dry run: nothing written.")
        left = unnamed_keys(keys, registry, owner if a.dry_run else _owner(names_file))
        print(
            f"{len(left)} clusters still unnamed."
            + ("" if a.dry_run else " Next: make build, make preview, make publish.")
        )
        return 0

    from pipeline.embed import load_embeddings
    from pipeline.snapshot import load_current
    from pipeline.textprep import protected_words

    X, ids, _ = load_embeddings(settings.data_dir / "embeddings")
    lay = np.load(model_dir / "layout.npz")
    if lay["ids"].tolist() != ids:
        ap.error("the model is out of date with the embeddings; run make cluster first")
    all_records = load_current(settings.data_dir / "raw")[0]
    records = {r["id"]: r for r in all_records}
    text = build_brief(
        keys,
        registry,
        owner,
        lay["labels"],
        X,
        np.load(model_dir / "centroids.npy"),
        ids,
        records,
        protected_words(all_records),
    )
    out = a.out or settings.data_dir / "runs" / meta["fit_run_id"] / "naming_brief.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    n = len(unnamed_keys(keys, registry, owner))
    print(f"Wrote {out} ({len(text) // 1024} KB, {n} clusters to name).")
    print(
        "Upload it to a chat, save the reply as a text file, then: make import-names FILE=<that file>"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
