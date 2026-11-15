import pytest

from pipeline.config import load_settings, require


def test_defaults_without_env_file(tmp_path, monkeypatch):
    for k in ["EMBEDDING_MODEL", "N_CLUSTERS", "CLOUDFLARE_API_TOKEN", "MLFLOW_PORT"]:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(tmp_path / "missing.env")
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.n_clusters == 120
    assert s.query_prefix == "Represent this sentence for searching relevant passages: "
    assert s.mlflow_port == 5001
    assert s.cloudflare_api_token is None


def test_env_overrides_file(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("N_CLUSTERS=60\n")
    monkeypatch.setenv("N_CLUSTERS", "200")
    assert load_settings(f).n_clusters == 200


def test_file_value_used_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("N_CLUSTERS", raising=False)
    f = tmp_path / ".env"
    f.write_text("N_CLUSTERS=60\n")
    assert load_settings(f).n_clusters == 60


def test_empty_string_counts_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
    monkeypatch.delenv("N_CLUSTERS", raising=False)
    f = tmp_path / ".env"
    f.write_text("N_CLUSTERS=\n")
    s = load_settings(f)
    assert s.cloudflare_api_token is None
    assert s.n_clusters == 120


def test_require_names_missing_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="missing required setting: CLOUDFLARE_API_TOKEN"):
        require(load_settings(tmp_path / "x.env"), "CLOUDFLARE_API_TOKEN")
