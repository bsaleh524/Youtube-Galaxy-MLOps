import numpy as np
import pytest

from pipeline import parity_check, workers_ai
from pipeline.config import load_settings


def test_cosine_rows_identical_and_orthogonal():
    a = np.array([[1, 0, 0], [0, 2, 0]], dtype=np.float32)
    b = np.array([[3, 0, 0], [5, 0, 0]], dtype=np.float32)
    assert np.allclose(parity_check.cosine_rows(a, b), [1.0, 0.0])


def test_main_without_credentials_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert parity_check.main([]) == 2
    assert "missing required setting: CLOUDFLARE_ACCOUNT_ID" in capsys.readouterr().err


def test_samples_file_has_20_passages_and_10_queries():
    s = parity_check.load_samples()
    assert len(s["passages"]) == 20 and len(s["queries"]) == 10
    assert all(p["url"].startswith("https://youtube.fandom.com/") for p in s["passages"])


def test_embed_remote_builds_request(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok456")
    calls = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "result": {"shape": [2, 3], "data": [[3, 0, 4], [0, 1, 0]]}}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json))
        return Resp()

    monkeypatch.setattr(workers_ai.requests, "post", fake_post)
    out = workers_ai.embed_remote(["a", "b"], load_settings(None), pooling="cls")
    url, headers, body = calls[0]
    assert "acc123" in url and "@cf/baai/bge-small-en-v1.5" in url and "tok456" not in url
    assert headers["Authorization"] == "Bearer tok456"
    assert headers["User-Agent"] == "galaxy-hobby-scraper/1.0"
    assert body == {"text": ["a", "b"], "pooling": "cls"}
    assert out.dtype == np.float32
    assert np.allclose(out, [[0.6, 0, 0.8], [0, 1, 0]])


def test_embed_remote_rejects_unknown_pooling():
    with pytest.raises(ValueError):
        workers_ai.embed_remote(["a"], load_settings(None), pooling="max")
