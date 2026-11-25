import json

import pytest

from pipeline import gate
from pipeline.gate import GateConfig, check, load_config, read_gate, write_gate

CFG = GateConfig(silhouette_floor=0.024, recall_tolerance=0.05, count_ratio=0.9, agreement_min=0.9)
SHA = "ab" * 32


def report(silhouette=0.03, recall=0.6, n_approved=10, creators=20000, agreement=0.97, sha=SHA):
    return {
        "version": "v2",
        "creators": creators,
        "silhouette": silhouette,
        "questions_sha256": sha,
        "summary": {
            "approved": {
                "n": n_approved,
                "recall_at_8": recall if n_approved else None,
                "mrr": 0.5,
            },
            "all": {"n": 30, "recall_at_8": 0.5, "mrr": 0.4},
            "agreement": agreement,
        },
    }


def prev(recall=0.6, creators=20000, sha=SHA):
    m = {"creators": float(creators)}
    if recall is not None:
        m["recall_at_8_approved"] = recall
    return {"version": "v1", "metrics": m, "params": {"questions_sha256": sha}}


def by_name(result):
    return {c["name"]: c for c in result["checks"]}


def test_all_pass():
    r = check(report(), prev(), CFG)
    assert r["passed"] is True and r["version"] == "v2"
    assert [c["name"] for c in r["checks"]] == ["silhouette", "recall", "creators", "agreement"]


def test_silhouette_below_floor_fails():
    c = by_name(check(report(silhouette=0.021), prev(), CFG))["silhouette"]
    assert c["passed"] is False and "0.021" in c["reason"] and "0.024" in c["reason"]


def test_silhouette_missing_fails():
    assert by_name(check(report(silhouette=None), prev(), CFG))["silhouette"]["passed"] is False


def test_recall_drop_beyond_tolerance_fails():
    r = check(report(recall=0.54), prev(recall=0.6), CFG)
    c = by_name(r)["recall"]
    assert r["passed"] is False and c["passed"] is False and "0.540" in c["reason"]
    assert by_name(check(report(recall=0.55), prev(recall=0.6), CFG))["recall"]["passed"] is True


def test_creator_drop_fails():
    c = by_name(check(report(creators=17000), prev(creators=20000), CFG))["creators"]
    assert c["passed"] is False and "17000" in c["reason"] and "18000" in c["reason"]


def test_zero_creators_fails_even_without_previous():
    assert by_name(check(report(creators=0), None, CFG))["creators"]["passed"] is False


def test_agreement_below_min_fails():
    c = by_name(check(report(agreement=0.85), prev(), CFG))["agreement"]
    assert c["passed"] is False and "0.850" in c["reason"]


def test_no_previous_publish():
    r = check(report(), None, CFG)
    assert r["passed"] is True
    for name in ("recall", "creators"):
        assert "no previous publish" in by_name(r)[name]["reason"]


def test_no_approved_questions_skips_recall():
    c = by_name(check(report(n_approved=0), prev(), CFG))["recall"]
    assert c["passed"] is True and c["reason"].startswith("skipped (no approved questions")


def test_champion_without_recall_skips():
    c = by_name(check(report(), prev(recall=None), CFG))["recall"]
    assert c["passed"] is True and c["reason"].startswith("skipped")


def test_changed_questions_skip_recall_comparison():
    c = by_name(check(report(recall=0.1), prev(recall=0.6, sha="cd" * 32), CFG))["recall"]
    assert c["passed"] is True and "questions changed" in c["reason"]


def test_missing_config_key(tmp_path):
    p = tmp_path / "gate.yaml"
    p.write_text("silhouette_floor: 0.02\nrecall_tolerance: 0.05\ncount_ratio: 0.9\n")
    with pytest.raises(ValueError, match="agreement_min"):
        load_config(p)


def test_gate_file_roundtrip(tmp_path):
    r = check(report(), None, CFG)
    path = write_gate(r, tmp_path)
    assert path == tmp_path / "eval-v2" / "gate.json"
    assert read_gate(tmp_path, "v2")["passed"] is True
    assert read_gate(tmp_path, "nope") is None


def test_main_exit_code_and_gate_file(tmp_path, monkeypatch, capsys):
    runs = tmp_path / "runs" / "eval-v2"
    runs.mkdir(parents=True)
    (runs / "report.json").write_text(json.dumps(report(silhouette=0.01)))
    cfg = tmp_path / "gate.yaml"
    cfg.write_text(
        "silhouette_floor: 0.024\nrecall_tolerance: 0.05\ncount_ratio: 0.9\nagreement_min: 0.9\n"
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gate, "previous_publish", lambda data_dir: None)
    assert gate.main(["--version", "v2", "--config", str(cfg)]) == 1
    out = capsys.readouterr()
    assert "FAIL" in out.err and "silhouette" in out.err
    assert json.loads((runs / "gate.json").read_text())["passed"] is False


def test_main_without_report_explains(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert gate.main(["--version", "v9", "--config", "eval/gate.yaml"]) == 1
    assert "make eval" in capsys.readouterr().err
