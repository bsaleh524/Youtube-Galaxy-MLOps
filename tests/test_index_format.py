import numpy as np
import pytest

from pipeline.index_format import (
    IndexData,
    quantize_rows,
    read_centroids,
    read_index,
    read_meta_record,
    write_centroids,
    write_index,
    write_meta,
)
from pipeline.synthetic import make_synthetic


def test_roundtrip_index(tmp_path):
    v, offsets, _cents, _recs = make_synthetic(n=200, dim=16, k=5, seed=0)
    q, s = quantize_rows(v)
    write_index(tmp_path / "index.bin", IndexData(q, s, offsets))
    d = read_index(tmp_path / "index.bin")
    assert np.array_equal(d.q, q)
    assert np.allclose(d.scales, s)
    assert np.array_equal(d.offsets, offsets)


def test_roundtrip_centroids(tmp_path):
    _, _, cents, _ = make_synthetic(n=200, dim=16, k=5, seed=0)
    write_centroids(tmp_path / "c.bin", cents)
    assert np.allclose(read_centroids(tmp_path / "c.bin"), cents)


def test_bad_magic_raises(tmp_path):
    (tmp_path / "x.bin").write_bytes(b"NOTMAGIC" + bytes(64))
    with pytest.raises(ValueError, match="bad magic"):
        read_index(tmp_path / "x.bin")


def test_quantization_cosine_error_small():
    v, *_ = make_synthetic(n=500, dim=384, k=10, seed=0)
    q, s = quantize_rows(v)
    approx = q.astype(np.float32) * (s / 127)[:, None]
    assert np.max(np.abs(np.sum(approx * v, 1) - 1.0)) < 0.01


def test_synthetic_is_cluster_ordered_and_normalised():
    v, offsets, cents, recs = make_synthetic(n=300, dim=16, k=6, seed=3)
    assert offsets[0] == 0 and offsets[-1] == 300 and np.all(np.diff(offsets) >= 0)
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-5)
    assert np.allclose(np.linalg.norm(cents, axis=1), 1, atol=1e-5)
    assert [r["cluster"] for r in recs] == [c for c in range(6) for _ in range(offsets[c], offsets[c + 1])]


def test_meta_utf8_byte_offsets(tmp_path):
    recs = [
        {"id": "fandom_1", "title": "ねくろちゃん -Yamaguro Nekuro-", "cluster": 0, "url": "u", "snippet": "🎮 ok"},
        {"id": "fandom_2", "title": "Plain", "cluster": 1, "url": "u2", "snippet": "x"},
    ]
    write_meta(tmp_path / "meta.bin", recs)
    blob = (tmp_path / "meta.bin").read_bytes()
    assert read_meta_record(blob, 0) == recs[0]
    assert read_meta_record(blob, 1) == recs[1]


def test_meta_duplicate_titles_distinct_ids(tmp_path):
    recs = [
        {"id": "fandom_449281", "title": "Target", "cluster": 0, "url": "a", "snippet": "x"},
        {"id": "fandom_372805", "title": "Target", "cluster": 0, "url": "b", "snippet": "y"},
    ]
    write_meta(tmp_path / "meta.bin", recs)
    blob = (tmp_path / "meta.bin").read_bytes()
    assert [read_meta_record(blob, i)["id"] for i in (0, 1)] == ["fandom_449281", "fandom_372805"]
