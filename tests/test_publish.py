import json
from pathlib import Path

import pytest

from pipeline import publish
from pipeline.publish import (
    LocalRemote,
    execute,
    galaxy_files,
    home_files,
    newest_build,
    plan_uploads,
)

V = "20261118-000000-abcdef12"
ALWAYS = {"manifest.json", "index.html", ".htaccess"}


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def build_dir(tmp_path):
    b = tmp_path / "artifacts" / "galaxy" / V
    _write(b / "manifest.json", json.dumps({"version": V}))
    _write(b / "nodes.json", '{"id": []}')
    _write(b / "clusters.json", "[]")
    _write(b / "neighbors.json", "{}")
    _write(b / "details" / "cluster_c001.json", "{}")
    _write(b / "worker" / "index.bin", "bin")
    return b


@pytest.fixture
def dist_dir(tmp_path):
    d = tmp_path / "dist"
    _write(d / "index.html", '<script src="/galaxy/assets/app-1a2b.js"></script>')
    _write(d / ".htaccess", "# rules")
    _write(d / "assets" / "app-1a2b.js", "js")
    return d


def test_galaxy_files_order(build_dir, dist_dir):
    files = galaxy_files(build_dir, dist_dir)
    paths = [p for p, _ in files]
    assert files[-1] == ("manifest.json", build_dir / "manifest.json")
    assert paths.index("index.html") > max(i for i, p in enumerate(paths) if p.startswith("assets/"))
    data = [p for p in paths if p not in ("manifest.json", "index.html", ".htaccess") and not p.startswith("assets/")]
    assert data and all(p.startswith(f"data/{V}/") for p in data)
    assert f"data/{V}/details/cluster_c001.json" in paths
    assert not any("worker" in p for p in paths)
    assert paths.count("manifest.json") == 1


def test_galaxy_files_data_only(build_dir):
    paths = [p for p, _ in galaxy_files(build_dir, None)]
    assert paths[-1] == "manifest.json"
    assert not any(p.startswith("assets/") or p in ("index.html", ".htaccess") for p in paths)


def test_home_files_top_level_sorted(tmp_path):
    h = tmp_path / "home"
    _write(h / "index.html", "x")
    _write(h / "home.css", "y")
    _write(h / "sub" / "z.html", "z")
    assert [p for p, _ in home_files(h)] == ["home.css", "index.html"]


def test_plan_skips_same_size_except_always(tmp_path, build_dir):
    remote = LocalRemote(tmp_path / "remote")
    _write(tmp_path / "remote" / f"data/{V}/nodes.json", (build_dir / "nodes.json").read_text())
    _write(tmp_path / "remote" / "manifest.json", (build_dir / "manifest.json").read_text())
    acts = {a.path: a.op for a in plan_uploads(galaxy_files(build_dir, None), remote, "", ALWAYS)}
    assert acts[f"data/{V}/nodes.json"] == "skip"
    assert acts["manifest.json"] == "put"
    assert acts[f"data/{V}/clusters.json"] == "put"


def test_plan_uses_base_prefix(tmp_path, build_dir):
    remote = LocalRemote(tmp_path / "remote")
    acts = plan_uploads(galaxy_files(build_dir, None), remote, "public_html/galaxy", ALWAYS)
    assert acts[-1].path == "public_html/galaxy/manifest.json"


def test_execute_writes_files(tmp_path, build_dir):
    remote = LocalRemote(tmp_path / "remote")
    execute(plan_uploads(galaxy_files(build_dir, None), remote, "", ALWAYS), remote, log=lambda s: None)
    assert (tmp_path / "remote" / "manifest.json").read_bytes() == (build_dir / "manifest.json").read_bytes()
    assert (tmp_path / "remote" / f"data/{V}/details/cluster_c001.json").exists()


class FailingRemote(LocalRemote):
    def __init__(self, root, fail_on):
        super().__init__(root)
        self.puts, self.fail_on = 0, fail_on

    def put(self, local, path):
        self.puts += 1
        if self.puts == self.fail_on:
            # leave a partial tmp file behind, the way a dropped connection would
            tmp = self.root / (path + ".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text("partial")
            raise OSError("connection lost")
        super().put(local, path)


def test_execute_stops_before_manifest_on_failure(tmp_path, build_dir):
    remote = FailingRemote(tmp_path / "remote", fail_on=2)
    acts = plan_uploads(galaxy_files(build_dir, None), remote, "", ALWAYS)
    with pytest.raises(OSError):
        execute(acts, remote, log=lambda s: None)
    assert not (tmp_path / "remote" / "manifest.json").exists()
    assert list((tmp_path / "remote").rglob("*.tmp")) == []


def test_newest_build(tmp_path):
    a = tmp_path / "a"
    for v in ["20261118-000000-aaaaaaaa", "20261119-000000-bbbbbbbb", ".20261120-000000-cccccccc.tmp"]:
        (a / v).mkdir(parents=True)
    assert newest_build(a).name == "20261119-000000-bbbbbbbb"


def test_stage_cli_writes_mirror(tmp_path, build_dir, dist_dir, monkeypatch):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    monkeypatch.setattr(publish, "ARTIFACTS_SUBDIR", Path("artifacts/galaxy"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    out = tmp_path / "stage"
    assert publish.main(["galaxy", "--to-dir", str(out), "--version", V]) == 0
    assert (out / "manifest.json").read_bytes() == (build_dir / "manifest.json").read_bytes()
    assert (out / "assets" / "app-1a2b.js").exists()


def test_stage_all_nests_galaxy_and_home(tmp_path, build_dir, dist_dir, monkeypatch):
    home = tmp_path / "home"
    _write(home / "index.html", "home")
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    monkeypatch.setattr(publish, "HOME_DIR", home)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOSTINGER_REMOTE_DIR", "public_html/galaxy")
    out = tmp_path / "stage"
    assert publish.main(["all", "--to-dir", str(out)]) == 0
    assert (out / "index.html").read_text() == "home"
    assert (out / "galaxy" / "manifest.json").exists()


def test_dry_run_writes_nothing(tmp_path, build_dir, dist_dir, monkeypatch, capsys):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    out = tmp_path / "stage"
    assert publish.main(["galaxy", "--data-only", "--to-dir", str(out), "--dry-run"]) == 0
    assert not out.exists() or not any(out.rglob("*"))
    assert "manifest.json" in capsys.readouterr().out
