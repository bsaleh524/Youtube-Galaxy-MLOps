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


def test_comment_text_is_not_read_as_a_value(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    f = tmp_path / ".env"
    f.write_text("CLOUDFLARE_API_TOKEN=          # Workers AI permission\n")
    assert load_settings(f).cloudflare_api_token is None


def test_env_example_leaves_every_secret_unset(monkeypatch):
    from pathlib import Path

    from dotenv import dotenv_values

    example = Path(__file__).resolve().parents[1] / ".env.example"
    values = dotenv_values(example)
    secrets = ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "WORKER_URL", "HOSTINGER_SFTP_HOST",
               "HOSTINGER_SFTP_USER", "HOSTINGER_SFTP_PASSWORD", "HOSTINGER_SFTP_KEY_PATH",
               "GROQ_API_KEY", "SYNOLOGY_BACKUP_DIR"]
    assert {k: values.get(k) for k in secrets if values.get(k)} == {}


HOSTINGER_ENV = ["HOSTINGER_SFTP_HOST", "HOSTINGER_SFTP_PORT", "HOSTINGER_SFTP_USER", "HOSTINGER_SFTP_PASSWORD",
                 "HOSTINGER_SFTP_KEY_PATH", "HOSTINGER_REMOTE_DIR", "HOSTINGER_HOME_DIR", "SITE_BASE_PATH",
                 "SITE_ORIGIN"]


def test_hostinger_defaults(tmp_path, monkeypatch):
    for k in HOSTINGER_ENV:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(tmp_path / "missing.env")
    assert s.hostinger_sftp_host is None
    assert s.hostinger_sftp_port is None
    assert s.hostinger_sftp_password is None
    assert s.hostinger_remote_dir == "public_html/galaxy"
    assert s.hostinger_home_dir == "public_html"
    assert s.site_base_path == "/galaxy/"
    assert s.site_origin == "https://spookypharaoh.com"


def test_hostinger_values_read_and_port_cast(tmp_path, monkeypatch):
    for k in HOSTINGER_ENV:
        monkeypatch.delenv(k, raising=False)
    f = tmp_path / ".env"
    f.write_text("HOSTINGER_SFTP_HOST=example.host\nHOSTINGER_SFTP_PORT=65002\nHOSTINGER_SFTP_USER=u1\n"
                 "HOSTINGER_SFTP_PASSWORD=\nHOSTINGER_REMOTE_DIR=public_html/galaxy\n")
    s = load_settings(f)
    assert (s.hostinger_sftp_host, s.hostinger_sftp_port, s.hostinger_sftp_user) == ("example.host", 65002, "u1")
    assert s.hostinger_sftp_password is None
