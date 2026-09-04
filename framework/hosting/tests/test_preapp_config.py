"""Tests for the pre-app host settings read.

The three failure modes exercised here — unreachable DB, reachable but
unmigrated DB, empty table — are the ordinary states of a fresh install, and
each one is what the setup wizard exists to repair. If any of them raised, the
wizard would be unreachable and the operator would be back to editing ``.env``
blind, which is the friction this whole change removes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from simple_module_hosting._preapp_config import (
    apply_host_overrides,
    load_host_overrides,
    merge_host_settings,
)
from simple_module_hosting.bootstrap_settings import BootstrapSettings

_CREATE = """
CREATE TABLE settings_setting (
    id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL
)
"""


def _seed(db_path: Path, rows: list[tuple[str, str, str]]) -> str:
    """Create the settings table and insert ``(key, value, value_type)`` rows."""
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE)
    conn.executemany(
        "INSERT INTO settings_setting (scope, scope_id, key, value, value_type) "
        "VALUES ('system', '', ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return f"sqlite+aiosqlite:///{db_path}"


def test_returns_empty_when_table_missing(tmp_path: Path) -> None:
    """An unmigrated DB falls back to defaults instead of raising."""
    db = tmp_path / "unmigrated.db"
    sqlite3.connect(db).close()  # file exists, no tables
    assert load_host_overrides(f"sqlite+aiosqlite:///{db}") == {}


def test_returns_empty_when_db_unreachable() -> None:
    """A wrong host must not fail the boot — the wizard reports it instead."""
    url = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing"
    assert load_host_overrides(url) == {}


def test_returns_empty_when_table_empty(tmp_path: Path) -> None:
    url = _seed(tmp_path / "empty.db", [])
    assert load_host_overrides(url) == {}


def test_reads_only_host_scoped_overrides(tmp_path: Path) -> None:
    """Rows belonging to other packages must not leak into host settings."""
    url = _seed(
        tmp_path / "seeded.db",
        [
            ("host.tenant_header", "X-Tenant", "string"),
            ("users.smtp_host", "mail.example.com", "string"),
        ],
    )
    assert load_host_overrides(url) == {"tenant_header": ("X-Tenant", "string")}


def test_skips_nested_keys(tmp_path: Path) -> None:
    """``host.a.b`` addresses a sub-object, not a top-level field."""
    url = _seed(tmp_path / "nested.db", [("host.a.b", "x", "string")])
    assert load_host_overrides(url) == {}


def test_apply_parses_by_value_type() -> None:
    out = apply_host_overrides(
        {"multi_tenant": ("true", "bool"), "tenant_header": ("X-T", "string")},
        environ={},
    )
    assert out == {"multi_tenant": True, "tenant_header": "X-T"}


def test_apply_drops_unknown_fields() -> None:
    """A stale row for a removed field must not blow up Settings()."""
    assert apply_host_overrides({"no_such_field": ("1", "string")}, environ={}) == {}


def test_apply_survives_unparseable_row() -> None:
    """One bad row falls back to the default rather than failing the boot."""
    out = apply_host_overrides(
        {"multi_tenant": ("true", "bool"), "i18n_supported_locales": ("not json", "json")},
        environ={},
    )
    assert out == {"multi_tenant": True}


def test_env_beats_db_override() -> None:
    """Precedence is env → DB → default; inverting it would silently change
    behaviour for every existing deployment on upgrade."""
    out = apply_host_overrides(
        {"tenant_header": ("from-db", "string")},
        environ={"SM_TENANT_HEADER": "from-env"},
    )
    assert out == {}


def test_db_applies_when_env_absent() -> None:
    out = apply_host_overrides({"tenant_header": ("from-db", "string")}, environ={})
    assert out == {"tenant_header": "from-db"}


@pytest.mark.parametrize("raw,expected", [("true", True), ("1", True), ("off", False)])
def test_bool_parsing(raw: str, expected: bool) -> None:
    out = apply_host_overrides({"multi_tenant": (raw, "bool")}, environ={})
    assert out["multi_tenant"] is expected


def test_merge_applies_db_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SM_TENANT_HEADER", raising=False)
    url = _seed(tmp_path / "merge.db", [("host.tenant_header", "X-From-Db", "string")])
    bootstrap = BootstrapSettings(_env_file=None, database_url=url)

    merged = merge_host_settings(bootstrap)

    assert merged.tenant_header == "X-From-Db"
    assert merged.database_url == url


def test_merge_keeps_env_winner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_TENANT_HEADER", "X-From-Env")
    url = _seed(tmp_path / "merge2.db", [("host.tenant_header", "X-From-Db", "string")])
    bootstrap = BootstrapSettings(_env_file=None, database_url=url)

    assert merge_host_settings(bootstrap).tenant_header == "X-From-Env"
