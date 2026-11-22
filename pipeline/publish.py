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
import stat
import sys
import time
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

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

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
    if done or skipped:
        log(f"uploaded {done}, unchanged {skipped}")


def format_actions(actions: list[Action]) -> str:
    return "\n".join(f"{a.op:6} {a.path}  ({a.reason})" for a in actions)


# ---------------------------------------------------------------- SFTP (Hostinger)

class SftpRemote:
    """Hostinger over SFTP. Host keys must already be in ~/.ssh/known_hosts (see docs/DEPLOY.md)."""

    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.sftp = None

    def __enter__(self):
        import paramiko  # imported here so the ci test group doesn't need it

        s = self.settings
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                s.hostinger_sftp_host, port=s.hostinger_sftp_port or 22, username=s.hostinger_sftp_user,
                password=None if s.hostinger_sftp_key_path else s.hostinger_sftp_password,
                key_filename=s.hostinger_sftp_key_path, look_for_keys=False, allow_agent=False, timeout=30,
            )
        except paramiko.SSHException as e:
            raise SystemExit(f"SFTP connection failed: {e}. If the host key is unknown, see docs/DEPLOY.md.") from None
        self.client, self.sftp = client, client.open_sftp()
        return self

    def __exit__(self, *exc):
        if self.client:
            self.client.close()

    def _stat(self, path: str):
        try:
            return self.sftp.stat(path)
        except OSError:
            return None

    def exists(self, path: str) -> bool:
        return self._stat(path) is not None

    def size(self, path: str) -> int | None:
        st = self._stat(path)
        return None if st is None or stat.S_ISDIR(st.st_mode) else st.st_size

    def listdir(self, path: str) -> list[str]:
        try:
            return sorted(self.sftp.listdir(path or "."))
        except OSError:
            return []

    def makedirs(self, path: str) -> None:
        parts = [x for x in path.split("/") if x]
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            if not self.exists(sub):
                self.sftp.mkdir(sub)

    def put(self, local: Path, path: str) -> None:
        self.makedirs(posixpath.dirname(path))
        tmp = path + ".tmp"
        self.sftp.put(str(local), tmp)
        try:
            self.sftp.posix_rename(tmp, path)
        except OSError:  # server without the posix-rename extension
            if self.exists(path):
                self.sftp.remove(path)
            self.sftp.rename(tmp, path)

    def remove(self, path: str) -> None:
        if self.exists(path):
            self.sftp.remove(path)

    def rmtree(self, path: str) -> None:
        for attr in self.sftp.listdir_attr(path):
            child = posixpath.join(path, attr.filename)
            if stat.S_ISDIR(attr.st_mode):
                self.rmtree(child)
            else:
                self.sftp.remove(child)
        self.sftp.rmdir(path)

    def read_text(self, path: str) -> str | None:
        try:
            with self.sftp.open(path, "r") as f:
                return f.read().decode("utf-8")
        except OSError:
            return None


# ---------------------------------------------------------------- checks, prune, verify

PLACEHOLDER_PAGES = ("default.php", "index.php")
USER_AGENT = "galaxy-publish/1.0"


def preflight(settings, build_dir: Path, dist_dir: Path | None, remote: Remote) -> list[str]:
    """Problems that stop a publish; entries starting with "warning: " only warn."""
    errors = []
    remote_dir = settings.hostinger_remote_dir.rstrip("/")
    if settings.site_base_path.strip("/") != posixpath.basename(remote_dir):
        errors.append(f"SITE_BASE_PATH {settings.site_base_path} does not match HOSTINGER_REMOTE_DIR {remote_dir}: "
                      "the site would be uploaded to one folder and look for its files in another")
    if settings.hostinger_home_dir.rstrip("/") != posixpath.dirname(remote_dir):
        errors.append(f"HOSTINGER_HOME_DIR {settings.hostinger_home_dir} must be the parent of "
                      f"HOSTINGER_REMOTE_DIR {remote_dir}")
    if dist_dir is not None:
        index = Path(dist_dir) / "index.html"
        if not index.exists() or f"{settings.site_base_path}assets/" not in index.read_text(encoding="utf-8"):
            errors.append(f"{index} was not built for {settings.site_base_path}; run `make web-build`")
    listed = json.loads((Path(build_dir) / "manifest.json").read_text(encoding="utf-8")).get("files", {})
    missing = [f for f in listed if not f.startswith("worker/") and not (Path(build_dir) / f).exists()]
    if missing:
        errors.append(f"build {Path(build_dir).name} is missing {len(missing)} file(s), e.g. {missing[0]}")
    present = [f for f in PLACEHOLDER_PAGES if f in remote.listdir(settings.hostinger_home_dir)]
    if present:
        errors.append(f"warning: {settings.hostinger_home_dir}/{present[0]} exists and may be shown instead of "
                      "the new index.html; delete it in hPanel's File Manager (docs/DEPLOY.md)")
    return errors


def live_version(remote: Remote, galaxy_dir: str) -> str | None:
    text = remote.read_text(_join(galaxy_dir, "manifest.json"))
    try:
        return json.loads(text)["version"] if text else None
    except (ValueError, KeyError):
        return None


def prune_plan(remote: Remote, galaxy_dir: str, live: str | None, keep: int = 3) -> list[Action]:
    """Remove data/<version> dirs beyond the `keep` newest; never the live one."""
    data = _join(galaxy_dir, "data")
    versions = sorted(remote.listdir(data))
    old = [v for v in versions[:-keep] if v != live] if len(versions) > keep else []
    return [Action("rmtree", _join(data, v), None, "older than the newest 3") for v in old]


def _http_get(url: str, headers: dict) -> bytes:
    import urllib.request

    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return r.read()


def verify(url: str, version: str, fetch: Callable[[str, dict], bytes] = _http_get) -> bool:
    """Does the public manifest report `version`? A cache-busting query avoids stale copies."""
    try:
        body = fetch(f"{url}?t={int(time.time())}", {"User-Agent": USER_AGENT})
        return json.loads(body).get("version") == version
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- CLI

def _open(a, settings):
    if a.to_dir is not None:
        return LocalRemote(a.to_dir), "", ""
    from pipeline.config import require

    require(settings, "HOSTINGER_SFTP_HOST", "HOSTINGER_SFTP_USER")
    if not (settings.hostinger_sftp_password or settings.hostinger_sftp_key_path):
        raise SystemExit("missing required setting: HOSTINGER_SFTP_PASSWORD or HOSTINGER_SFTP_KEY_PATH (set it in .env)")
    remote = SftpRemote(settings)
    return remote, settings.hostinger_home_dir.rstrip("/"), settings.hostinger_remote_dir.rstrip("/")


def _rollback(a, settings, artifacts: Path, log) -> int:
    build_dir = artifacts / a.version_arg
    if not (build_dir / "manifest.json").exists():
        log(f"no local build {a.version_arg} in {artifacts}; its manifest is needed for a rollback")
        return 1
    ctx, _, galaxy_base = _open(a, settings)
    with ctx as remote:
        if not remote.exists(_join(galaxy_base, f"data/{a.version_arg}/nodes.json")):
            log(f"version {a.version_arg} is not on the server (only the newest 3 are kept)")
            return 1
        acts = plan_uploads([("manifest.json", build_dir / "manifest.json")], remote, galaxy_base, ALWAYS_GALAXY)
        if a.dry_run:
            print(format_actions(acts))
            return 0
        execute(acts, remote, log=log)
    return _verify_live(a, settings, a.version_arg, log)


def _verify_live(a, settings, version: str, log) -> int:
    if a.to_dir is not None:
        return 0
    url = f"{settings.site_origin.rstrip('/')}{settings.site_base_path}manifest.json"
    if verify(url, version):
        log(f"live: {url} reports {version}")
        return 0
    log(f"WARNING: {url} does not report {version} yet; check it in a browser")
    return 1


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["galaxy", "home", "all", "rollback"])
    ap.add_argument("version_arg", nargs="?", metavar="VERSION", help="for rollback: the version to switch to")
    ap.add_argument("--to-dir", type=Path, help="write to this local folder instead of Hostinger")
    ap.add_argument("--data-only", action="store_true", help="galaxy data + manifest only (no web/dist)")
    ap.add_argument("--version", help="build version to publish (default: newest in data/artifacts/galaxy)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written; write nothing")
    a = ap.parse_args(argv)
    log = lambda s: print(s, file=sys.stderr)

    settings = load_settings()
    artifacts = settings.data_dir / ARTIFACTS_SUBDIR
    if a.target == "rollback":
        if not a.version_arg:
            ap.error("rollback needs a VERSION")
        return _rollback(a, settings, artifacts, log)

    build_dir = artifacts / a.version if a.version else newest_build(artifacts)
    if not (build_dir / "manifest.json").exists():
        ap.error(f"no build at {build_dir}")
    version = _version(build_dir)
    with_galaxy = a.target in ("galaxy", "all")
    dist = DIST_DIR if with_galaxy and not a.data_only else None
    ctx, home_base, galaxy_base = _open(a, settings)
    if a.to_dir is not None and a.target == "all":
        galaxy_base = posixpath.basename(settings.hostinger_remote_dir.rstrip("/"))

    with ctx as remote:
        if with_galaxy:
            problems = preflight(settings, build_dir, dist, remote)
            for p in problems:
                log(p)
            if any(not p.startswith("warning: ") for p in problems):
                return 1
        actions: list[Action] = []
        if a.target in ("home", "all"):
            actions += plan_uploads(home_files(HOME_DIR), remote, home_base, ALWAYS_HOME)
        if with_galaxy:
            actions += plan_uploads(galaxy_files(build_dir, dist), remote, galaxy_base, ALWAYS_GALAXY)
        where = a.to_dir or f"{settings.hostinger_sftp_host}:{home_base}"
        log(f"build {version} -> {where}")
        if a.dry_run:
            print(format_actions(actions))
            if with_galaxy:
                prune = prune_plan(remote, galaxy_base, version)
                if prune:
                    print(format_actions(prune))
            return 0
        execute(actions, remote, log=log)
        if not with_galaxy:
            return 0
        if _verify_live(a, settings, version, log):
            return 1  # leave old versions in place until the new one is confirmed live
        execute(prune_plan(remote, galaxy_base, version), remote, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
