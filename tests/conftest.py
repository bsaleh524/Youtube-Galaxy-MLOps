import pytest

import pipeline.config


@pytest.fixture(autouse=True)
def _no_real_env_file(monkeypatch):
    """Tests must never read the developer's real .env (it holds Hostinger credentials)."""
    monkeypatch.setattr(pipeline.config, "ENV_FILE", None)

