"""Lay out the site for Hostinger and write it to a remote (or to a local mirror).

    uv run python -m pipeline.publish galaxy|home|all [--to-dir DIR] [--data-only] [--version V] [--dry-run]

Hostinger tree (relative to the home dir, public_html/):

    index.html, home.css                 home page (web/home/, top-level files only)
    galaxy/index.html, .htaccess          web/dist, built with SITE_BASE_PATH=/galaxy/
    galaxy/assets/<hashed files>
    galaxy/data/<version>/...             one Plan 2 build, minus worker/
    galaxy/manifest.json                  the pointer: a copy of the build's manifest, uploaded LAST

`--to-dir DIR` writes the same tree into a local folder (`make stage`, `make web-data`).
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

DIST_DIR = Path("web/dist")
HOME_DIR = Path("web/home")
ARTIFACTS_SUBDIR = Path("artifacts/galaxy")
ALWAYS_GALAXY = frozenset({"manifest.json", "index.html", ".htaccess"})
ALWAYS_HOME = frozenset({"index.html"})


# ---------------------------------------------------------------- layout

def newest_build(artifacts: Path) -> Path:
    builds = sorted(p for p in Path(artifacts).iterdir() if p.is_dir() and not p.name.startswith("."))
    if not builds:
        raise FileNotFoundError(f"no builds in {artifacts}; run `make build` first")
    return builds[-1]


def _version(build_dir: Path) -> str:
    return json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))["version"]


def _files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def galaxy_files(build_dir: Path, dist_dir: Path | None) -> list[tuple[str, Path]]:
    """(path relative to the galaxy dir, local file), in upload order; manifest.json last."""
    build_dir = Path(build_dir)
    version = _version(build_dir)
    out: list[tuple[str, Path]] = []
    for p in _files_under(build_dir):
        rel = p.relative_to(build_dir).as_posix()
        if rel == "manifest.json" or rel.startswith("worker/"):
            continue
        out.append((f"data/{version}/{rel}", p))
    if dist_dir is not None:
        dist_dir = Path(dist_dir)
        last = []
        for p in _files_under(dist_dir):
            rel = p.relative_to(dist_dir).as_posix()
            if rel in (".htaccess", "index.html"):
                last.append((rel, p))
            else:
                out.append((rel, p))
        out.extend(sorted(last))  # ".htaccess" sorts before "index.html"
    out.append(("manifest.json", build_dir / "manifest.json"))
    return out


def home_files(home_dir: Path) -> list[tuple[str, Path]]:
    return [(p.name, p) for p in sorted(Path(home_dir).iterdir()) if p.is_file() and not p.name.startswith(".")]


# ---------------------------------------------------------------- remotes

class Remote(Protocol):
    def exists(self, path: str) -> bool: ...
    def size(self, path: str) -> int | None: ...
    def listdir(self, path: str) -> list[str]: ...
    def makedirs(self, path: str) -> None: ...
    def put(self, local: Path, path: str) -> None: ...
    def remove(self, path: str) -> None: ...
    def rmtree(self, path: str) -> None: ...
    def read_text(self, path: str) -> str | None: ...


class LocalRemote:
    """A folder on this machine laid out exactly like the Hostinger tree."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _p(self, path: str) -> Path:
        return self.root / path

    def exists(self, path: str) -> bool:
        return self._p(path).exists()

    def size(self, path: str) -> int | None:
        p = self._p(path)
        return p.stat().st_size if p.is_file() else None

    def listdir(self, path: str) -> list[str]:
        p = self._p(path)
        return sorted(x.name for x in p.iterdir()) if p.is_dir() else []

    def makedirs(self, path: str) -> None:
        self._p(path).mkdir(parents=True, exist_ok=True)

    def put(self, local: Path, path: str) -> None:
        dest = self._p(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        shutil.copyfile(local, tmp)
        os.replace(tmp, dest)

    def remove(self, path: str) -> None:
        self._p(path).unlink(missing_ok=True)

    def rmtree(self, path: str) -> None:
        shutil.rmtree(self._p(path), ignore_errors=True)

    def read_text(self, path: str) -> str | None:
        p = self._p(path)
        return p.read_text(encoding="utf-8") if p.is_file() else None


# ---------------------------------------------------------------- plan and execute

@dataclass
class Action:
    op: Literal["put", "skip", "rmtree"]
    path: str
    local: Path | None
    reason: str


def _join(base: str, rel: str) -> str:
    return posixpath.join(base, rel) if base else rel


def plan_uploads(files: list[tuple[str, Path]], remote: Remote, base: str, always: set[str] | frozenset[str]
                 ) -> list[Action]:
    """Skip a file the remote already has at the same size, except paths in `always`."""
    actions = []
    for rel, local in files:
        path = _join(base, rel)
        size = local.stat().st_size
        if rel not in always and remote.size(path) == size:
            actions.append(Action("skip", path, local, "same size on remote"))
        else:
            actions.append(Action("put", path, local, f"{size / 1e6:.2f} MB"))
    return actions


def execute(actions: list[Action], remote: Remote, log: Callable[[str], None] = print) -> None:
    """Run in order; stop at the first failure (so manifest.json, which is last, is never uploaded)."""
    done = skipped = 0
    for a in actions:
        if a.op == "skip":
            skipped += 1
        elif a.op == "rmtree":
            remote.rmtree(a.path)
            log(f"removed {a.path}")
        else:
            try:
                remote.put(a.local, a.path)
            except BaseException:
                try:
                    remote.remove(a.path + ".tmp")
                except OSError as e:  # best effort; the original error matters more
                    log(f"could not remove {a.path}.tmp: {e}")
                raise
            done += 1
    log(f"uploaded {done}, unchanged {skipped}")


def format_actions(actions: list[Action]) -> str:
    return "\n".join(f"{a.op:6} {a.path}  ({a.reason})" for a in actions)


# ---------------------------------------------------------------- CLI

def _plans(target: str, settings, build_dir: Path, data_only: bool, remote: Remote, galaxy_base: str,
           home_base: str) -> list[Action]:
    actions: list[Action] = []
    if target in ("home", "all"):
        actions += plan_uploads(home_files(HOME_DIR), remote, home_base, ALWAYS_HOME)
    if target in ("galaxy", "all"):
        dist = None if data_only else DIST_DIR
        if dist is not None and not (Path(dist) / "index.html").exists():
            raise SystemExit(f"{dist}/index.html not found; run `make web-build` first (or pass --data-only)")
        actions += plan_uploads(galaxy_files(build_dir, dist), remote, galaxy_base, ALWAYS_GALAXY)
    return actions


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["galaxy", "home", "all"])
    ap.add_argument("--to-dir", type=Path, help="write to this local folder instead of Hostinger")
    ap.add_argument("--data-only", action="store_true", help="galaxy data + manifest only (no web/dist)")
    ap.add_argument("--version", help="build version (default: newest in data/artifacts/galaxy)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written; write nothing")
    a = ap.parse_args(argv)

    settings = load_settings()
    artifacts = settings.data_dir / ARTIFACTS_SUBDIR
    build_dir = artifacts / a.version if a.version else newest_build(artifacts)
    if not (build_dir / "manifest.json").exists():
        ap.error(f"no build at {build_dir}")
    if a.to_dir is None:
        ap.error("--to-dir is required (uploading to Hostinger is not built yet)")

    remote = LocalRemote(a.to_dir)
    galaxy_base = posixpath.basename(settings.hostinger_remote_dir.rstrip("/")) if a.target == "all" else ""
    actions = _plans(a.target, settings, build_dir, a.data_only, remote, galaxy_base, "")
    log = lambda s: print(s, file=sys.stderr)
    print(f"build {build_dir.name} -> {a.to_dir}", file=sys.stderr)
    if a.dry_run:
        print(format_actions(actions))
        return 0
    execute(actions, remote, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
