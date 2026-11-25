import json

import pytest

from pipeline.run import current_inputs, run
from pipeline.snapshot import write_snapshot


def setup(tmp_path):
    recs = [{"id": "fandom_1", "title": "A", "description": "", "thumbnail": None, "youtube_url": None, "url": "u"}]
    write_snapshot(recs, tmp_path / "raw", "test")
    model = tmp_path / "model" / "galaxy"
    model.mkdir(parents=True)
    (model / "model.json").write_text(json.dumps({"fit_run_id": "fit1"}))


def record_build(tmp_path, name="20261118-000000-aaaaaaaa"):
    b = tmp_path / "artifacts" / "galaxy" / name
    b.mkdir(parents=True)
    (b / "manifest.json").write_text(json.dumps({"inputs": current_inputs(tmp_path)}))


def steps(calls):
    return [(n, lambda argv, n=n: calls.append(n) or 0) for n in ("embed", "cluster", "build")]


def test_runs_all_steps_when_never_built(tmp_path):
    setup(tmp_path)
    calls = []
    out = run(tmp_path, steps(calls), log=lambda s: None)
    assert calls == ["embed", "cluster", "build"] and out["skipped"] is False


def test_skips_when_inputs_unchanged(tmp_path):
    setup(tmp_path)
    record_build(tmp_path)
    calls, logs = [], []
    out = run(tmp_path, steps(calls), log=logs.append)
    assert calls == [] and out["skipped"] is True and "nothing changed" in logs[0]


@pytest.mark.parametrize("change", ["names", "refit", "snapshot"])
def test_reruns_when_an_input_changes(tmp_path, change):
    setup(tmp_path)
    record_build(tmp_path)
    if change == "names":
        (tmp_path / "cluster_names.json").write_text('{"c001": "Mine"}')
    elif change == "refit":
        (tmp_path / "model" / "galaxy" / "model.json").write_text(json.dumps({"fit_run_id": "fit2"}))
    else:
        recs = [{"id": "fandom_2", "title": "B", "description": "", "thumbnail": None, "youtube_url": None, "url": "u"}]
        write_snapshot(recs, tmp_path / "raw", "test")
    calls = []
    assert run(tmp_path, steps(calls), log=lambda s: None)["skipped"] is False and len(calls) == 3


def test_force_and_failing_step(tmp_path):
    setup(tmp_path)
    record_build(tmp_path)
    calls = []
    assert run(tmp_path, steps(calls), force=True, log=lambda s: None)["skipped"] is False
    with pytest.raises(SystemExit, match="cluster failed"):
        run(tmp_path, [("embed", lambda a: 0), ("cluster", lambda a: 2)], force=True, log=lambda s: None)


def test_run_steps_include_evaluate_and_gate():
    from pipeline.run import STEP_NAMES

    assert STEP_NAMES == ["embed", "cluster", "build", "evaluate", "gate"]
