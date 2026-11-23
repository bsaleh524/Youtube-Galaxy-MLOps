import numpy as np
import pytest

from pipeline.sanity import (
    SANITY_IDS,
    chance_rate,
    fold_words,
    format_report,
    lookalike,
    lookalike_rate,
    score,
)


def test_fold_words():
    assert fold_words("Pokémon Café – Él") == ["pokemon", "cafe"]


def test_lookalike_examples():
    assert lookalike("Marques Brownlee", "Brownie")
    assert lookalike("Kurzgesagt – In a Nutshell", "KuruHS")
    assert lookalike("Markiplier", "LS Mark")
    assert not lookalike("Dream", "Sapnap")
    assert not lookalike("Ed", "Ed")  # words under 3 chars are ignored


def test_rate_counts_pairs():
    titles = ["Alex A", "Alexa", "Zed"]
    nbrs = np.array([[1, 2], [0, 2], [0, 1]])
    assert lookalike_rate(titles, nbrs) == pytest.approx(2 / 6)


def test_chance_rate_is_deterministic_and_bounded():
    titles = ["Alex", "Alexa", "Bob", "Bobby", "Zed"]
    a, b = chance_rate(titles, n_pairs=2000), chance_rate(titles, n_pairs=2000)
    assert a == b and 0 < a < 1


def test_score_shape_on_small_matrix():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(30, 8)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    ids = [SANITY_IDS[0]] + [f"fandom_{i}" for i in range(29)]
    titles = ["Dream"] + [f"creator {i}" for i in range(29)]
    out = score(X, ids, titles, k=3)
    assert set(out) >= {"lookalike_rate", "chance_rate", "silhouette", "checks"}
    assert list(out["checks"]) == [SANITY_IDS[0]]  # sanity ids not in the data are skipped
    assert len(out["checks"][SANITY_IDS[0]]["neighbours"]) == 10
    md = format_report(out, "test")
    assert "Dream" in md and "lookalike" in md
