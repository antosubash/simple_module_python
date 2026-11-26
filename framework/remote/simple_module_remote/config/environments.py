"""Named environments: load, merge defaults, save, and pick one."""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import tomli_w

from simple_module_remote.config.paths import config_dir, env_prefix

CONFIG_FILENAME = "config.toml"
ENV_NAME_RE = re.compile(r"^[a-z0-9-]+$")
ENV_TABLE = "env"


class ConfigError(Exception):
    """Raised for unusable configuration; the message is safe to show."""


def validate_env_name(name: str) -> str:
    if not ENV_NAME_RE.fullmatch(name):
        raise ConfigError(f"invalid environment name {name!r}: use lowercase letters, digits, '-'")
    return name


@dataclass(frozen=True)
class Environment:
    name: str
    url: str
    tenant: str | None = None
    protected: bool = False

    @property
    def origin(self) -> str:
        parts = urlsplit(self.url)
        return f"{parts.scheme}://{parts.netloc}"


@dataclass
class Config:
    current: str | None = None
    envs: dict[str, Environment] = field(default_factory=dict)
    # Names the user file defines or edited; only these are written back.
    user_envs: set[str] = field(default_factory=set)


def _read(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc


def _env_tables(data: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = data.get(ENV_TABLE, {})
    if not isinstance(raw, dict):
        return {}
    return {validate_env_name(str(k)): v for k, v in raw.items() if isinstance(v, dict)}


def _build(name: str, table: dict[str, object], base: Environment | None) -> Environment:
    url = table.get("url", base.url if base else None)
    if not isinstance(url, str) or not url:
        raise ConfigError(f"environment {name!r} has no url")
    tenant = table.get("tenant", base.tenant if base else None)
    protected = table.get("protected", base.protected if base else False)
    return Environment(
        name=name,
        url=url,
        tenant=tenant if isinstance(tenant, str) else None,
        protected=protected is True,
    )


def user_config_path(cli: str) -> Path:
    return config_dir(cli) / CONFIG_FILENAME


def load_config(cli: str, defaults_path: Path | None) -> Config:
    defaults = _read(defaults_path)
    user = _read(user_config_path(cli))
    envs: dict[str, Environment] = {}
    for name, table in _env_tables(defaults).items():
        envs[name] = _build(name, table, None)
    user_tables = _env_tables(user)
    for name, table in user_tables.items():
        envs[name] = _build(name, table, envs.get(name))
    current = user.get("current", defaults.get("current"))
    return Config(
        current=current if isinstance(current, str) else None,
        envs=envs,
        user_envs=set(user_tables),
    )


def save_config(cli: str, config: Config) -> None:
    path = user_config_path(cli)
    tables: dict[str, dict[str, object]] = {}
    for name in sorted(config.user_envs):
        env = config.envs.get(name)
        if env is None:
            continue
        table: dict[str, object] = {"url": env.url, "protected": env.protected}
        if env.tenant is not None:
            table["tenant"] = env.tenant
        tables[name] = table
    data: dict[str, object] = {}
    if config.current is not None:
        data["current"] = config.current
    if tables:
        data[ENV_TABLE] = tables
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def select_env(
    config: Config, flag: str | None, environ: Mapping[str, str], cli: str
) -> tuple[Environment, bool]:
    var = f"{env_prefix(cli)}_ENV"
    from_var = environ.get(var) or None
    name, explicit = flag or from_var, bool(flag or from_var)
    if not name:
        name = config.current
    if not name:
        raise ConfigError(f"no environment selected: run `{cli} env use <name>` or pass --env")
    env = config.envs.get(name)
    if env is None:
        known = ", ".join(sorted(config.envs)) or "none"
        raise ConfigError(
            f"unknown environment {name!r} (known: {known}): run `{cli} env add {name} --url ...`"
        )
    return env, explicit
