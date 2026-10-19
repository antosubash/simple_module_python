"""A stored host setting that parses but no longer validates must not stop boot.

Before #497 ``merge_host_settings`` called ``Settings(**values)`` unguarded, so
one stale row — a ``Literal`` narrowed in an upgrade, say — took down every
worker, and with them the admin UI that could fix the row.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from simple_module_hosting import _secret_key
from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting.bootstrap_settings import BootstrapSettings

_LOGGER = "simple_module_core.stored_settings"


def _seed(db_path: Path, rows: list[tuple[str, str, str]]) -> str:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE settings_setting (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, "
        "scope_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
        "value_type TEXT NOT NULL, UNIQUE (scope, scope_id, key))"
    )
    conn.executemany(
        "INSERT INTO settings_setting (scope, scope_id, key, value, value_type) "
        "VALUES ('system', '', ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SM_LOG_FORMAT", "SM_TENANT_HEADER", "SM_SECRET_KEY", "SM_I18N_DEFAULT_LOCALE"):
        monkeypatch.delenv(name, raising=False)


def test_invalid_literal_boots_with_default_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    url = _seed(
        tmp_path / "xml.db",
        [("host.log_format", "xml", "string"), ("host.tenant_header", "X-T", "string")],
    )
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        merged = merge_host_settings(BootstrapSettings(_env_file=None, database_url=url))

    assert merged.log_format == "json"
    assert merged.tenant_header == "X-T", "the valid sibling override must survive"
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("log_format" in m for m in warned)
    assert not any("xml" in m for m in warned), "never echo the stored value"


def test_model_level_error_drops_the_stored_half(tmp_path: Path) -> None:
    """``i18n_default_locale`` outside the supported list is a model error with
    no field location; the related-fields context names what to drop."""
    url = _seed(tmp_path / "locale.db", [("host.i18n_default_locale", "fr", "string")])
    merged = merge_host_settings(BootstrapSettings(_env_file=None, database_url=url))
    assert merged.i18n_default_locale == "en"


def test_stored_secret_key_needs_no_second_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key is a ``host.*`` row, so the overrides read already carries it."""
    url = _seed(tmp_path / "key.db", [("host.secret_key", "k" * 64, "string")])

    async def _no_second_trip(_url: str) -> str:
        raise AssertionError("ensure_secret_key reopened the database")

    monkeypatch.setattr(_secret_key, "_ensure", _no_second_trip)
    merged = merge_host_settings(BootstrapSettings(_env_file=None, database_url=url))
    assert merged.secret_key == "k" * 64
