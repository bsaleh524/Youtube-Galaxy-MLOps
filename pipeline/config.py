"""Settings loaded from `.env` (optional) with environment variables taking precedence."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

from dotenv import dotenv_values

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass(frozen=True)
class Settings:
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    n_clusters: int = 120
    query_prefix: str = QUERY_PREFIX
    data_dir: Path = Path("data")
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    mlflow_port: int = 5001


# Settings field -> environment variable name. query_prefix is fixed, not configurable.
_ENV_NAMES = {
    "embedding_model": "EMBEDDING_MODEL",
    "n_clusters": "N_CLUSTERS",
    "data_dir": "DATA_DIR",
    "cloudflare_account_id": "CLOUDFLARE_ACCOUNT_ID",
    "cloudflare_api_token": "CLOUDFLARE_API_TOKEN",
    "mlflow_port": "MLFLOW_PORT",
}
_CASTS = {"n_clusters": int, "mlflow_port": int, "data_dir": Path}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_settings(env_file: Path | None = Path(".env")) -> Settings:
    file_values = dotenv_values(env_file) if env_file and Path(env_file).exists() else {}
    kwargs = {}
    for field_name, env_name in _ENV_NAMES.items():
        value = _clean(os.environ.get(env_name))
        if value is None:
            value = _clean(file_values.get(env_name))
        if value is not None:
            kwargs[field_name] = _CASTS.get(field_name, str)(value)
    return Settings(**kwargs)


def require(settings: Settings, *names: str) -> None:
    """Exit with a one-line message naming the first unset setting (by env-var name)."""
    by_env = {env: f for f, env in _ENV_NAMES.items()}
    valid = {f.name for f in fields(Settings)}
    for name in names:
        attr = by_env.get(name, name.lower())
        if attr not in valid:
            raise ValueError(f"unknown setting: {name}")
        if getattr(settings, attr) in (None, ""):
            raise SystemExit(f"missing required setting: {name} (set it in .env)")
