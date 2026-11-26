from pathlib import Path

import pytest
from simple_module_remote.config.environments import (
    Config,
    ConfigError,
    Environment,
    load_config,
    save_config,
    select_env,
    validate_env_name,
)
from simple_module_remote.config.paths import env_prefix

CLI = "smdev"


@pytest.fixture
def xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / CLI


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_defaults_merge_user_wins(xdg: Path, tmp_path: Path) -> None:
    defaults = _write(
        tmp_path / "defaults.toml",
        '[env.prod]\nurl = "https://prod.example"\nprotected = true\n'
        '[env.dev]\nurl = "http://localhost:8000"\n',
    )
    _write(xdg / "config.toml", 'current = "dev"\n[env.prod]\nurl = "https://other.example"\n')
    cfg = load_config(CLI, defaults)
    assert cfg.current == "dev"
    assert cfg.envs["prod"].url == "https://other.example"
    assert cfg.envs["prod"].protected is True  # per-key merge
    assert cfg.envs["dev"].url == "http://localhost:8000"


def test_select_precedence_flag_env_current() -> None:
    cfg = Config(
        current="a",
        envs={n: Environment(n, f"https://{n}.example") for n in ("a", "b", "c")},
    )
    assert select_env(cfg, None, {}, CLI)[0].name == "a"
    assert select_env(cfg, None, {"SMDEV_ENV": "b"}, CLI)[0].name == "b"
    assert select_env(cfg, "c", {"SMDEV_ENV": "b"}, CLI)[0].name == "c"


def test_select_explicit_flag() -> None:
    cfg = Config(current="a", envs={"a": Environment("a", "https://a.example")})
    assert select_env(cfg, None, {}, CLI)[1] is False
    assert select_env(cfg, "a", {}, CLI)[1] is True
    assert select_env(cfg, None, {"SMDEV_ENV": "a"}, CLI)[1] is True


@pytest.mark.parametrize("name", ["Prod", "../x", "", "a b"])
def test_invalid_env_name_rejected(name: str) -> None:
    with pytest.raises(ConfigError):
        validate_env_name(name)


def test_no_env_hint_names_env_use() -> None:
    with pytest.raises(ConfigError, match="env use"):
        select_env(Config(), None, {}, CLI)


def test_save_does_not_copy_defaults(xdg: Path, tmp_path: Path) -> None:
    defaults = _write(tmp_path / "defaults.toml", '[env.prod]\nurl = "https://prod.example"\n')
    cfg = load_config(CLI, defaults)
    cfg.current = "prod"
    save_config(CLI, cfg)
    text = (xdg / "config.toml").read_text()
    assert "prod.example" not in text
    assert 'current = "prod"' in text


def test_save_roundtrip_user_env(xdg: Path) -> None:
    cfg = Config(
        envs={"stage": Environment("stage", "https://s.example", tenant="t1", protected=True)},
        user_envs={"stage"},
    )
    save_config(CLI, cfg)
    loaded = load_config(CLI, None)
    assert loaded.envs["stage"] == cfg.envs["stage"]


def test_origin() -> None:
    assert Environment("a", "https://h.example:8443/base").origin == "https://h.example:8443"


def test_env_prefix() -> None:
    assert env_prefix("my-app") == "MY_APP"


@pytest.mark.parametrize("value", ['"true"', "1"])
def test_protected_must_be_bool(xdg: Path, value: str) -> None:
    _write(xdg / "config.toml", f'[env.prod]\nurl = "https://p.example"\nprotected = {value}\n')
    with pytest.raises(ConfigError, match=r"prod.*protected"):
        load_config(CLI, None)


def test_tenant_must_be_string(xdg: Path) -> None:
    _write(xdg / "config.toml", '[env.prod]\nurl = "https://p.example"\ntenant = 5\n')
    with pytest.raises(ConfigError, match=r"prod.*tenant"):
        load_config(CLI, None)


def test_malformed_toml(xdg: Path) -> None:
    _write(xdg / "config.toml", "[env.prod\n")
    with pytest.raises(ConfigError, match="cannot read config"):
        load_config(CLI, None)


def test_env_without_url(xdg: Path) -> None:
    _write(xdg / "config.toml", "[env.prod]\nprotected = true\n")
    with pytest.raises(ConfigError, match="no url"):
        load_config(CLI, None)


def test_save_leaves_no_temp_file(xdg: Path) -> None:
    save_config(CLI, Config(current="a"))
    assert [p.name for p in xdg.iterdir()] == ["config.toml"]
