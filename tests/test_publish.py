import json
from pathlib import Path

import pytest

from pipeline import publish
from pipeline.config import Settings
from pipeline.publish import (
    LocalRemote,
    execute,
    galaxy_files,
    home_files,
    live_version,
    newest_build,
    plan_uploads,
    preflight,
    prune_plan,
    verify,
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


# ---------------------------------------------------------------- Task 7: preflight, prune, rollback, verify


def _settings(**kw) -> Settings:
    return Settings(**kw)


def test_preflight_ok(build_dir, dist_dir, tmp_path):
    assert preflight(_settings(), build_dir, dist_dir, LocalRemote(tmp_path / "remote")) == []


def test_preflight_base_path_mismatch(build_dir, dist_dir, tmp_path):
    errs = preflight(_settings(site_base_path="/map/"), build_dir, dist_dir, LocalRemote(tmp_path / "r"))
    assert any("/map/" in e and "public_html/galaxy" in e for e in errs)


def test_preflight_dist_built_with_wrong_base(build_dir, dist_dir, tmp_path):
    (dist_dir / "index.html").write_text('<script src="/assets/app-1a2b.js"></script>')
    errs = preflight(_settings(), build_dir, dist_dir, LocalRemote(tmp_path / "r"))
    assert any("make web-build" in e for e in errs)


def test_preflight_home_dir_must_be_parent(build_dir, dist_dir, tmp_path):
    errs = preflight(_settings(hostinger_home_dir="www"), build_dir, dist_dir, LocalRemote(tmp_path / "r"))
    assert any("HOSTINGER_HOME_DIR" in e for e in errs)


def test_preflight_missing_build_file(build_dir, dist_dir, tmp_path):
    m = json.loads((build_dir / "manifest.json").read_text())
    m["files"] = {"nodes.json": 1, "gone.json": 1, "worker/index.bin": 1}
    (build_dir / "manifest.json").write_text(json.dumps(m))
    errs = preflight(_settings(), build_dir, dist_dir, LocalRemote(tmp_path / "r"))
    assert len(errs) == 1 and "gone.json" in errs[0]


def test_preflight_warns_on_placeholder_index(build_dir, dist_dir, tmp_path):
    _write(tmp_path / "r" / "public_html" / "default.php", "<?php")
    errs = preflight(_settings(), build_dir, dist_dir, LocalRemote(tmp_path / "r"))
    assert len(errs) == 1 and errs[0].startswith("warning: ") and "default.php" in errs[0]


def test_home_plan_touches_only_own_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _write(home / "index.html", "new home")
    _write(home / "home.css", "css")
    remote_root = tmp_path / "r"
    others = {"galaxy/manifest.json": "{}", "music/x.html": "music", ".htaccess": "root rules"}
    for rel, text in others.items():
        _write(remote_root / rel, text)
    before = {p.relative_to(remote_root).as_posix(): p.read_bytes() for p in remote_root.rglob("*") if p.is_file()}
    remote = LocalRemote(remote_root)
    execute(plan_uploads(home_files(home), remote, "", publish.ALWAYS_HOME), remote, log=lambda s: None)
    after = {p.relative_to(remote_root).as_posix(): p.read_bytes() for p in remote_root.rglob("*") if p.is_file()}
    changed = {k for k in after if before.get(k) != after[k]}
    assert changed == {"index.html", "home.css"}
    assert all(after[k] == before[k] for k in others)


def test_prune_keeps_three_and_live(tmp_path):
    root = tmp_path / "r"
    for v in ["v1", "v2", "v3", "v4", "v5"]:
        _write(root / "galaxy" / "data" / v / "nodes.json", "{}")
    acts = prune_plan(LocalRemote(root), "galaxy", "v1", keep=3)
    assert [(a.op, a.path) for a in acts] == [("rmtree", "galaxy/data/v2")]


def test_prune_nothing_when_few(tmp_path):
    root = tmp_path / "r"
    for v in ["v1", "v2"]:
        _write(root / "data" / v / "nodes.json", "{}")
    assert prune_plan(LocalRemote(root), "", "v2") == []


def test_live_version(tmp_path):
    root = tmp_path / "r"
    remote = LocalRemote(root)
    assert live_version(remote, "galaxy") is None
    _write(root / "galaxy" / "manifest.json", json.dumps({"version": "v7"}))
    assert live_version(remote, "galaxy") == "v7"


def _remote_with_versions(tmp_path, versions, live):
    root = tmp_path / "remote"
    for v in versions:
        _write(root / "data" / v / "nodes.json", "{}")
    _write(root / "manifest.json", json.dumps({"version": live}))
    return root


def test_rollback_requires_remote_version(tmp_path, build_dir, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    root = _remote_with_versions(tmp_path, ["v2"], "v2")
    before = (root / "manifest.json").read_bytes()
    assert publish.main(["rollback", V, "--to-dir", str(root)]) == 1
    assert (root / "manifest.json").read_bytes() == before
    assert "not on the server" in capsys.readouterr().err


def test_rollback_switches_manifest_only(tmp_path, build_dir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    root = _remote_with_versions(tmp_path, [V, "v9"], "v9")
    files_before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert publish.main(["rollback", V, "--to-dir", str(root)]) == 0
    assert json.loads((root / "manifest.json").read_text())["version"] == V
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == files_before


def test_dry_run_never_prints_secrets(tmp_path, build_dir, dist_dir, monkeypatch, capsys):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    home = tmp_path / "home"
    _write(home / "index.html", "home")
    monkeypatch.setattr(publish, "HOME_DIR", home)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k, v in {"HOSTINGER_SFTP_HOST": "sftp.example", "HOSTINGER_SFTP_PORT": "65002",
                 "HOSTINGER_SFTP_USER": "u123", "HOSTINGER_SFTP_PASSWORD": "s3cret-pw"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(publish, "SftpRemote", lambda settings: LocalRemote(tmp_path / "fake-sftp"))
    assert publish.main(["all", "--dry-run"]) == 0
    out = capsys.readouterr()
    assert "s3cret-pw" not in out.out + out.err
    assert "public_html/galaxy/manifest.json" in out.out
    assert not (tmp_path / "fake-sftp").exists()


def test_sftp_publish_needs_credentials(tmp_path, build_dir, dist_dir, monkeypatch, capsys):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k in ["HOSTINGER_SFTP_HOST", "HOSTINGER_SFTP_USER", "HOSTINGER_SFTP_PASSWORD", "HOSTINGER_SFTP_KEY_PATH"]:
        monkeypatch.setenv(k, "")
    with pytest.raises(SystemExit, match="HOSTINGER_SFTP_HOST"):
        publish.main(["galaxy"])


def test_verify():
    seen = []

    def fake(url, headers):
        seen.append((url, headers))
        return json.dumps({"version": "v2"}).encode()

    url = "https://spookypharaoh.com/galaxy/manifest.json"
    assert verify(url, "v2", fetch=fake) is True
    assert verify(url, "v1", fetch=fake) is False
    assert seen[0][0].startswith(url + "?t=")
    assert seen[0][1]["User-Agent"] == "galaxy-publish/1.0"


def test_verify_network_error_is_false():
    def boom(url, headers):
        raise OSError("down")

    assert verify("https://x.example/manifest.json", "v1", fetch=boom) is False


# ---------------------------------------------------------------- final-review fixes

def test_publish_keeps_previously_live_version_after_rollback(tmp_path, build_dir, dist_dir, monkeypatch):
    """Rolled back to the oldest version, then published: open pages still use that version."""
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    old = ["20260101-000000-aaaaaaaa", "20260102-000000-bbbbbbbb", "20260103-000000-cccccccc"]
    root = _remote_with_versions(tmp_path, old, old[0])
    assert publish.main(["galaxy", "--to-dir", str(root)]) == 0
    kept = sorted(p.name for p in (root / "data").iterdir())
    assert old[0] in kept and V in kept


def test_home_files_always_uploaded(tmp_path, monkeypatch):
    """home.css isn't versioned: an edit that keeps the same size must still go up."""
    home = tmp_path / "home"
    _write(home / "index.html", "home")
    _write(home / "home.css", "a{color:#1d1d36}")
    monkeypatch.setattr(publish, "HOME_DIR", home)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "artifacts" / "galaxy" / V).mkdir(parents=True)
    _write(tmp_path / "artifacts" / "galaxy" / V / "manifest.json", json.dumps({"version": V}))
    out = tmp_path / "site"
    assert publish.main(["home", "--to-dir", str(out)]) == 0
    _write(home / "home.css", "a{color:#2a2a40}")
    assert publish.main(["home", "--to-dir", str(out)]) == 0
    assert (out / "home.css").read_text() == "a{color:#2a2a40}"


def test_all_uploads_galaxy_before_home(tmp_path, build_dir, dist_dir, monkeypatch, capsys):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    home = tmp_path / "home"
    _write(home / "index.html", "home")
    monkeypatch.setattr(publish, "HOME_DIR", home)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOSTINGER_REMOTE_DIR", "public_html/galaxy")
    assert publish.main(["all", "--to-dir", str(tmp_path / "s"), "--dry-run"]) == 0
    lines = capsys.readouterr().out.splitlines()
    pos = {line.split()[1]: n for n, line in enumerate(lines)}
    assert pos["galaxy/manifest.json"] < pos["index.html"]


def test_home_not_uploaded_when_galaxy_fails(tmp_path, build_dir, dist_dir, monkeypatch):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    home = tmp_path / "home"
    _write(home / "index.html", "home")
    monkeypatch.setattr(publish, "HOME_DIR", home)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    out = tmp_path / "s"
    monkeypatch.setattr(publish, "LocalRemote", lambda root: FailingRemote(root, fail_on=2))
    with pytest.raises(OSError):
        publish.main(["all", "--to-dir", str(out)])
    assert not (out / "index.html").exists()


def test_sftp_key_path_must_exist(tmp_path, build_dir, dist_dir, monkeypatch):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k, v in {"HOSTINGER_SFTP_HOST": "sftp.example", "HOSTINGER_SFTP_USER": "u1",
                 "HOSTINGER_SFTP_PASSWORD": "pw", "HOSTINGER_SFTP_KEY_PATH": str(tmp_path / "nope")}.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit, match="HOSTINGER_SFTP_KEY_PATH"):
        publish.main(["galaxy", "--dry-run"])


# ---------------------------------------------------------------- Plan 4: Worker deploy

WORKER_FILES = ["index.bin", "centroids.bin", "meta.bin", "index_manifest.json"]


def _worker_build(build_dir):
    for name in WORKER_FILES:
        _write(build_dir / "worker" / name, f"new {name}")
    return build_dir


def test_stage_worker_copies_the_four_files(tmp_path, build_dir):
    assets = tmp_path / "assets"
    _write(assets / "index.bin", "stale")
    assert publish.stage_worker(_worker_build(build_dir), assets) == WORKER_FILES
    for name in WORKER_FILES:
        assert (assets / name).read_text() == f"new {name}"


def test_stage_worker_names_a_missing_file(tmp_path, build_dir):
    _worker_build(build_dir)
    (build_dir / "worker" / "meta.bin").unlink()
    with pytest.raises(FileNotFoundError, match="meta.bin"):
        publish.stage_worker(build_dir, tmp_path / "assets")


def test_deploy_worker_runs_wrangler_and_fails_loudly(tmp_path):
    calls = []

    class Done:
        def __init__(self, rc):
            self.returncode = rc

    def run(cmd, cwd):
        calls.append((cmd, cwd))
        return Done(0)

    publish.deploy_worker(tmp_path, run=run)
    assert calls == [(["npx", "wrangler", "deploy"], tmp_path)]
    with pytest.raises(RuntimeError):
        publish.deploy_worker(tmp_path, run=lambda cmd, cwd: Done(1))


def test_verify_worker_retries_until_the_version_shows():
    answers = iter([OSError("down"), json.dumps({"index_version": "old"}).encode(),
                    json.dumps({"ok": True, "index_version": V}).encode()])
    seen, sleeps = [], []

    def fetch(url, headers):
        seen.append(url)
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    assert publish.verify_worker("https://x.workers.dev", V, fetch=fetch, tries=5, sleep=sleeps.append)
    assert seen[0].startswith("https://x.workers.dev/health")
    assert len(sleeps) == 2


def test_verify_worker_gives_up():
    sleeps = []
    ok = publish.verify_worker("https://x", V, fetch=lambda u, h: b'{"index_version": "old"}', tries=3,
                               sleep=sleeps.append)
    assert ok is False and len(sleeps) == 2


def test_worker_dry_run_runs_nothing(tmp_path, build_dir, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(publish, "WORKER_ASSETS", tmp_path / "assets")
    monkeypatch.setattr(publish, "deploy_worker", lambda *a, **k: pytest.fail("deployed on a dry run"))
    _worker_build(build_dir)
    assert publish.main(["worker", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert all(name in out for name in WORKER_FILES) and "wrangler deploy" in out
    assert not (tmp_path / "assets").exists()


def test_worker_stage_only_never_deploys(tmp_path, build_dir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(publish, "WORKER_ASSETS", tmp_path / "assets")
    monkeypatch.setattr(publish, "deploy_worker", lambda *a, **k: pytest.fail("deployed on --stage-only"))
    _worker_build(build_dir)
    assert publish.main(["worker", "--stage-only"]) == 0
    assert (tmp_path / "assets" / "meta.bin").exists()


def _all_env(tmp_path, build_dir, dist_dir, monkeypatch, worker_url):
    monkeypatch.setattr(publish, "DIST_DIR", dist_dir)
    home = tmp_path / "home"
    _write(home / "index.html", "home")
    monkeypatch.setattr(publish, "HOME_DIR", home)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    if worker_url:
        monkeypatch.setenv("WORKER_URL", worker_url)
    else:
        monkeypatch.delenv("WORKER_URL", raising=False)
    root = tmp_path / "remote"
    monkeypatch.setattr(publish, "_open", lambda a, s: (publish.LocalRemote(root), "", "galaxy"))
    monkeypatch.setattr(publish, "verify", lambda url, version: True)
    order = []
    real_execute = publish.execute
    monkeypatch.setattr(publish, "execute", lambda acts, remote, log=print: (order.append("hostinger"),
                                                                            real_execute(acts, remote, log)))
    return order


def test_all_deploys_the_worker_before_hostinger(tmp_path, build_dir, dist_dir, monkeypatch):
    order = _all_env(tmp_path, build_dir, dist_dir, monkeypatch, "https://x.workers.dev")
    monkeypatch.setattr(publish, "_publish_worker", lambda s, b, log: order.append("worker") or 0)
    assert publish.main(["all"]) == 0
    assert order[0] == "worker" and "hostinger" in order


def test_all_without_worker_url_skips_the_worker(tmp_path, build_dir, dist_dir, monkeypatch):
    _all_env(tmp_path, build_dir, dist_dir, monkeypatch, None)
    monkeypatch.setattr(publish, "_publish_worker", lambda *a: pytest.fail("worker touched"))
    assert publish.main(["all"]) == 0


def test_all_stops_before_hostinger_when_the_worker_check_fails(tmp_path, build_dir, dist_dir, monkeypatch):
    order = _all_env(tmp_path, build_dir, dist_dir, monkeypatch, "https://x.workers.dev")
    monkeypatch.setattr(publish, "_publish_worker", lambda s, b, log: 1)
    assert publish.main(["all"]) == 1
    assert "hostinger" not in order
