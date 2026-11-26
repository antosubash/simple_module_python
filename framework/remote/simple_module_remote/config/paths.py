"""Where a CLI keeps its config and cache, and how its env vars are named."""

import os
from pathlib import Path


def _base(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def config_dir(cli: str) -> Path:
    return _base("XDG_CONFIG_HOME", ".config") / cli


def cache_dir(cli: str) -> Path:
    return _base("XDG_CACHE_HOME", ".cache") / cli


def env_prefix(cli: str) -> str:
    return cli.upper().replace("-", "_")
