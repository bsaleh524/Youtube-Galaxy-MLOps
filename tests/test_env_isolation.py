import pipeline.config


def test_real_env_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("HOSTINGER_SFTP_HOST=real.example\n")
    monkeypatch.delenv("HOSTINGER_SFTP_HOST", raising=False)
    assert pipeline.config.load_settings().hostinger_sftp_host is None
