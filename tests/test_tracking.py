import json

import pytest

pytest.importorskip("mlflow")

from pipeline import tracking


def _report(version, recall=0.5):
    return {
        "version": version,
        "creators": 12,
        "silhouette": 0.03,
        "search_params": {"k": 8, "probe_min": 3, "min_candidates": 1500, "max_probe": 12},
        "questions_sha256": "ab" * 32,
        "summary": {
            "approved": {"n": 2, "recall_at_8": recall, "mrr": 0.4},
            "all": {"n": 3, "recall_at_8": 0.6, "mrr": None},
            "agreement": 0.97,
        },
        "per_question": [],
    }


def _build(tmp_path, version):
    b = tmp_path / "artifacts" / "galaxy" / version
    (b / "worker").mkdir(parents=True)
    (b / "manifest.json").write_text(json.dumps({"version": version}))
    (b / "worker" / "index_manifest.json").write_text(json.dumps({"version": version}))
    return b


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return tmp_path / "data"


def test_champion_none_when_unset(data_dir):
    assert tracking.champion(data_dir) is None


def test_log_then_champion_roundtrip(data_dir, tmp_path):
    run_id = tracking.log_eval(_report("v1"), _build(tmp_path, "v1"), data_dir)
    assert run_id
    assert tracking.set_champion(data_dir, "v1") == "1"
    c = tracking.champion(data_dir)
    assert c["version"] == "v1" and c["run_id"] == run_id
    assert c["metrics"]["recall_at_8_approved"] == 0.5
    assert c["metrics"]["creators"] == 12
    assert "mrr_all" not in c["metrics"]  # null metrics are skipped


def test_set_champion_moves_alias(data_dir, tmp_path):
    tracking.log_eval(_report("v1"), _build(tmp_path, "v1"), data_dir)
    tracking.log_eval(_report("v2", recall=0.7), _build(tmp_path, "v2"), data_dir)
    tracking.set_champion(data_dir, "v1")
    tracking.set_champion(data_dir, "v2")
    c = tracking.champion(data_dir)
    assert c["version"] == "v2" and c["metrics"]["recall_at_8_approved"] == 0.7


def test_set_champion_without_eval_run_returns_none(data_dir):
    assert tracking.set_champion(data_dir, "never-evaluated") is None


def test_artifacts_land_under_data_dir(data_dir, tmp_path):
    tracking.log_eval(_report("v1"), _build(tmp_path, "v1"), data_dir)
    assert not (tmp_path / "cwd" / "mlruns").exists()
    files = {p.name for p in (data_dir / "mlflow" / "artifacts").rglob("*") if p.is_file()}
    assert {"report.json", "report.md", "manifest.json", "index_manifest.json"} <= files
    assert (data_dir / "mlflow" / "mlflow.db").exists()
