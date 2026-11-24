import pytest

from pipeline.evalset import load_questions, overlap, recall_at_k, reciprocal_rank, summarize

IDS = ["fandom_1", "fandom_2", "fandom_3", "fandom_4"]
TITLES = ["Vsauce", "Vsauce", "Mark Rober", "Café Crème"]


def _write(tmp_path, text):
    p = tmp_path / "q.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_recall_and_rr():
    assert recall_at_k(["x", "a", "y"], ["a", "b"]) == 0.5
    assert reciprocal_rank(["x", "a", "y"], ["a", "b"]) == 0.5
    assert recall_at_k(["x"], ["a"]) == 0.0
    assert reciprocal_rank(["x"], ["a"]) == 0.0
    # only the top k count
    got = [f"n{i}" for i in range(8)] + ["a"]
    assert recall_at_k(got, ["a"], k=8) == 0.0
    assert reciprocal_rank(got, ["a"], k=8) == 0.0


def test_overlap():
    assert overlap([1, 2, 3, 4], [1, 2, 5, 6]) == 0.5
    assert overlap([], []) == 0.0


def test_load_resolves_titles_ids_unknown_and_duplicates(tmp_path):
    p = _write(
        tmp_path,
        """
- question: science
  expected: [vsauce, fandom_3, "cafe creme", Nobody Here, fandom_999]
  status: draft
  notes: why
""",
    )
    (q,) = load_questions(p, IDS, TITLES)
    assert q.question == "science"
    assert q.expected_ids == ["fandom_1", "fandom_2", "fandom_3", "fandom_4"]
    assert q.unknown == ["Nobody Here", "fandom_999"]
    assert q.status == "draft"
    assert q.notes == "why"


def test_bad_status_raises(tmp_path):
    p = _write(tmp_path, "- {question: q1, expected: [Vsauce], status: maybe}\n")
    with pytest.raises(ValueError, match="q1"):
        load_questions(p, IDS, TITLES)


def test_question_with_no_known_expected_is_kept_but_flagged(tmp_path):
    p = _write(tmp_path, "- {question: q1, expected: [Ghost], status: approved}\n")
    (q,) = load_questions(p, IDS, TITLES)
    assert q.expected_ids == []
    assert q.unknown == ["Ghost"]


def test_summarize_zero_approved_is_null():
    rows = [
        {"status": "draft", "expected": ["a"], "recall_at_8": 1.0, "rr": 0.5, "agreement": 1.0},
        {"status": "draft", "expected": [], "recall_at_8": None, "rr": None, "agreement": 0.5},
    ]
    s = summarize(rows)
    assert s["approved"] == {"n": 0, "recall_at_8": None, "mrr": None}
    assert s["all"] == {
        "n": 1,
        "recall_at_8": 1.0,
        "mrr": 0.5,
    }  # questions without expected ids are excluded
    assert s["agreement"] == 0.75


def test_summarize_approved_means():
    rows = [
        {"status": "approved", "expected": ["a"], "recall_at_8": 1.0, "rr": 1.0, "agreement": 1.0},
        {"status": "approved", "expected": ["b"], "recall_at_8": 0.0, "rr": 0.0, "agreement": 1.0},
        {"status": "draft", "expected": ["c"], "recall_at_8": 1.0, "rr": 1.0, "agreement": 1.0},
    ]
    s = summarize(rows)
    assert s["approved"] == {"n": 2, "recall_at_8": 0.5, "mrr": 0.5}
    assert s["all"]["n"] == 3
