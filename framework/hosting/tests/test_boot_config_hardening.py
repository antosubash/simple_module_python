"""Boot-config paths that used to fail open or crash (follow-up to #494/#497).

Each case here once turned an error into a silent default on an established
install: a typo'd boolean read as ``False``, a broken settings import read as
"not installed", a failed key lookup minted a per-worker key, a failed module
hydrate poisoned the session for every later module, and a raising setup
check reopened the setup wizard on a live system.
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_settings import BaseSettings
from simple_module_core.setup_steps import SetupRegistry, SetupStep
from simple_module_core.stored_settings import parse_stored_value
from simple_module_hosting import _secret_key
from simple_module_hosting._hydrate_step import hydrate_all
from simple_module_hosting._lifespan import _is_first_run
from simple_module_hosting._preapp_config import (
    HostSettingsUnavailableError,
    apply_host_overrides,
    load_host_overrides,
)
from simple_module_hosting._secret_key import SecretKeyUnavailableError, ensure_secret_key
from simple_module_hosting.setup_gate import STEP_MIGRATIONS


def _settings_db(db_path: Path, rows: list[tuple[str, str]]) -> str:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE settings_setting (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, "
        "scope_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
        "value_type TEXT NOT NULL, UNIQUE (scope, scope_id, key))"
    )
    conn.executemany(
        "INSERT INTO settings_setting (scope, scope_id, key, value, value_type) "
        "VALUES ('system', '', ?, ?, 'string')",
        rows,
    )
    conn.commit()
    conn.close()
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SM_SECRET_KEY", raising=False)


# ── 1. Booleans parse strictly ─────────────────────────────


@pytest.mark.parametrize(("raw", "expected"), [("True", True), (" off ", False), ("0", False)])
def test_known_bool_tokens(raw: str, expected: bool) -> None:
    assert parse_stored_value(raw, "bool") is expected


def test_typo_bool_is_dropped_not_coerced_to_false(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        out = apply_host_overrides({"multi_tenant": ("tru", "bool")}, environ={})
    assert "multi_tenant" not in out
    assert "multi_tenant" in caplog.text


# ── 2. A broken settings import is a failure, not "not installed" ──


def test_settings_import_error_is_a_read_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.import_module

    def broken(name: str, *args, **kwargs):
        if name == "settings.constants":
            raise ImportError("circular import in settings")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", broken)
    with pytest.raises(HostSettingsUnavailableError):
        load_host_overrides("sqlite+aiosqlite:///:memory:", strict=True)


# ── 3. Ephemeral secret keys only on a confirmed fresh install ──


async def _lookup_fails(_url: str) -> str:
    raise OSError("Connection refused")


def test_key_lookup_failure_refuses_boot_when_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_secret_key, "_ensure", _lookup_fails)
    with pytest.raises(SecretKeyUnavailableError):
        ensure_secret_key("sqlite+aiosqlite:///:memory:", strict=True)


def test_key_lookup_failure_falls_back_in_development(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(_secret_key, "_ensure", _lookup_fails)
    with caplog.at_level(logging.WARNING):
        assert ensure_secret_key("sqlite+aiosqlite:///:memory:")
    assert "OSError" in caplog.text


def test_fresh_install_may_use_an_ephemeral_key_when_strict(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    sqlite3.connect(db).close()  # no tables: never migrated
    assert ensure_secret_key(f"sqlite+aiosqlite:///{db}", strict=True)


def test_no_settings_module_refuses_when_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_secret_key, "_settings_table", lambda: None)
    with pytest.raises(SecretKeyUnavailableError, match="SM_SECRET_KEY"):
        ensure_secret_key("sqlite+aiosqlite:///:memory:", strict=True)


def test_blank_stored_key_is_repaired_once(tmp_path: Path) -> None:
    """A blank row used to defeat the insert forever: an ephemeral key per boot."""
    db = tmp_path / "blank.db"
    url = _settings_db(db, [("host.secret_key", "")])

    key = ensure_secret_key(url, stored="", strict=True)

    assert key
    stored = sqlite3.connect(db).execute(
        "SELECT value FROM settings_setting WHERE key = 'host.secret_key'"
    )
    assert stored.fetchone()[0] == key
    assert ensure_secret_key(url, strict=True) == key, "a second boot reads the same key"


# ── 4. One module's failed hydrate does not poison the rest ──


class _A(BaseSettings):
    flag: bool = False


class _B(BaseSettings):
    flag: bool = False


async def test_failed_hydrate_rolls_back_and_continues() -> None:
    class _Store:
        async def get_overrides(self, package: str) -> dict[str, tuple[str, str]]:
            if package == "a":
                raise OSError("current transaction is aborted")
            return {"flag": ("true", "bool")}

    registry = SimpleNamespace(items=lambda: [("a", _A), ("b", _B)])
    a_before = _A()
    state = SimpleNamespace(
        settings=SimpleNamespace(module_registry=registry),
        a=SimpleNamespace(settings=a_before),
        b=SimpleNamespace(settings=_B()),
    )
    session = SimpleNamespace(rollback=AsyncMock())

    await hydrate_all(SimpleNamespace(state=state), _Store(), session)

    session.rollback.assert_awaited_once()
    assert state.a.settings is a_before, "a failed read keeps what the module had"
    assert state.b.settings.flag is True


# ── 5. A raising setup check needs evidence of a new install ──


def _raising_registry() -> SetupRegistry:
    async def done(_app) -> bool:
        return False

    async def boom(_app) -> bool:
        raise RuntimeError("connection reset")

    registry = SetupRegistry()
    registry.add(SetupStep(id=STEP_MIGRATIONS, title="m", is_complete=done))
    registry.add(SetupStep(id="users.administrator", title="admin", is_complete=boom))
    return registry


@pytest.mark.parametrize(("current_revision", "first_run"), [(None, True), ("abc123", False)])
async def test_raising_step_counts_as_first_run_only_without_history(
    current_revision: str | None, first_run: bool
) -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(setup_registry=_raising_registry()),
            migration={"current_revision": current_revision},
        )
    )
    assert await _is_first_run(app) is first_run
