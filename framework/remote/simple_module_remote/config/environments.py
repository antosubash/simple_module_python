"""Named environments: load, merge defaults, save, and pick one."""

import contextlib
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from simple_module_remote.config.paths import config_dir, env_url_var_name, env_var_name
from simple_module_remote.http.errors import UnsafePathError
from simple_module_remote.http.safety import normalize_origin, normalize_url, validate_base_url
from simple_module_remote.output.reasons import os_reason

CONFIG_FILENAME = "config.toml"
ENV_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MAX_TENANT_LEN = 128
ENV_TABLE = "env"


class ConfigError(Exception):
    """Raised for unusable configuration; the message is safe to show."""


def validate_env_name(name: str) -> str:
    if not ENV_NAME_RE.fullmatch(name):
        raise ConfigError(
            f"invalid environment name {name!r}: 1-40 lowercase letters, digits or '-', "
            "starting with a letter or digit"
        )
    return name


def validate_tenant(tenant: str) -> str:
    """A tenant slug or id: printable, no whitespace, bounded."""
    if (
        not tenant
        or len(tenant) > MAX_TENANT_LEN
        or not tenant.isprintable()
        or any(ch.isspace() for ch in tenant)
    ):
        raise ConfigError(
            f"invalid tenant {tenant!r}: up to {MAX_TENANT_LEN} printable characters, no spaces"
        )
    return tenant


@dataclass(frozen=True)
class Environment:
    name: str
    url: str
    tenant: str | None = None
    protected: bool = False

    @property
    def origin(self) -> str:
        return normalize_origin(self.url)


@dataclass
class Config:
    current: str | None = None
    envs: dict[str, Environment] = field(default_factory=dict)
    # Names the user file defines or edited; only these are written back.
    user_envs: set[str] = field(default_factory=set)
    # The keys the user file sets per environment; defaults fill in the rest, so only
    # what the user passed is written back.
    overrides: dict[str, dict[str, object]] = field(default_factory=dict)


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
    if tenant is not None and not isinstance(tenant, str):
        raise ConfigError(f"environment {name!r}: 'tenant' must be a string")
    protected = table.get("protected", base.protected if base else False)
    if not isinstance(protected, bool):
        raise ConfigError(f"environment {name!r}: 'protected' must be true or false")
    return Environment(name=name, url=normalize_url(url), tenant=tenant, protected=protected)


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
        overrides={name: dict(table) for name, table in user_tables.items()},
    )


def _user_table(config: Config, env: Environment) -> dict[str, object]:
    if env.name in config.overrides:
        return dict(config.overrides[env.name])
    table: dict[str, object] = {"url": env.url, "protected": env.protected}
    if env.tenant is not None:
        table["tenant"] = env.tenant
    return table


def save_config(cli: str, config: Config) -> None:
    path = user_config_path(cli)
    tables = {
        name: _user_table(config, env)
        for name in sorted(config.user_envs)
        if (env := config.envs.get(name)) is not None
    }
    data: dict[str, object] = {}
    if config.current is not None:
        data["current"] = config.current
    if tables:
        data[ENV_TABLE] = tables
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise ConfigError(f"cannot write config {path}: {os_reason(exc)}") from None
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def select_env(
    config: Config, flag: str | None, environ: Mapping[str, str], cli: str
) -> tuple[Environment, bool]:
    var = env_var_name(cli)
    from_var = environ.get(var) or None
    name, explicit = flag or from_var, bool(flag or from_var)
    if not name:
        name = config.current
    if not name:
        raise ConfigError(f"no environment selected: run `{cli} env use <name>` or pass --env")
    env = config.envs.get(name)
    url = environ.get(env_url_var_name(cli))
    if env is None and explicit and url:
        # CI: the runner has no config file; the URL variable defines the named environment.
        try:
            return Environment(name=validate_env_name(name), url=validate_base_url(url)), True
        except UnsafePathError as exc:
            raise ConfigError(f"{env_url_var_name(cli)}: {exc}") from None
    if env is None:
        known = ", ".join(sorted(config.envs)) or "none"
        raise ConfigError(
            f"unknown environment {name!r} (known: {known}): run `{cli} env add {name} --url ...` "
            f"or set {env_url_var_name(cli)} to define it for this run"
        )
    return env, explicit
