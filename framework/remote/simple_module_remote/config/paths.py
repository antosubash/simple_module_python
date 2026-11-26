"""Where a CLI keeps its config, and how its env vars are named."""

import os
from pathlib import Path


def _base(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def config_dir(cli: str) -> Path:
    return _base("XDG_CONFIG_HOME", ".config") / cli


def cache_dir(cli: str) -> Path:
    """Where *cli* caches downloaded data (the live schema): never credentials."""
    return _base("XDG_CACHE_HOME", ".cache") / cli


def env_prefix(cli: str) -> str:
    return cli.upper().replace("-", "_")


def env_var_name(cli: str) -> str:
    """The environment variable that selects the environment for *cli*."""
    return f"{env_prefix(cli)}_ENV"


def env_url_var_name(cli: str) -> str:
    """The variable that gives the URL of an environment that is not configured (CI)."""
    return f"{env_prefix(cli)}_URL"
