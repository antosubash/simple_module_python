"""Installation identity uses the same race-safe store as the root secret (#986)."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from _hosting_settings_db import seed_settings_db, unmigrated_db_url


@pytest.mark.parametrize("existing", [None, "", " \t"])
def test_identity_is_stored_once_and_survives_secret_rotation(tmp_path, monkeypatch, existing):
    from simple_module_hosting.config.installation import load_installation_id

    rows = [] if existing is None else [("host.installation_id", existing, "string")]
    url = seed_settings_db(tmp_path / "app.db", rows)
    first = load_installation_id(url)
    assert first
    monkeypatch.setenv("SM_SECRET_KEY", "rotated-root")
    assert load_installation_id(url) == first
    with sqlite3.connect(tmp_path / "app.db") as connection:
        assert connection.execute(
            "SELECT value FROM settings_setting WHERE scope='system' AND scope_id='' "
            "AND key='host.installation_id'"
        ).fetchall() == [(first,)]


def test_separate_databases_have_separate_identities(tmp_path):
    from simple_module_hosting.config.installation import load_installation_id

    first = seed_settings_db(tmp_path / "one.db", [])
    second = seed_settings_db(tmp_path / "two.db", [])
    assert load_installation_id(first) != load_installation_id(second)


def test_concurrent_boots_read_the_winning_identity(tmp_path):
    from simple_module_hosting.config.installation import load_installation_id

    url = seed_settings_db(tmp_path / "app.db", [])
    with ThreadPoolExecutor(max_workers=4) as pool:
        identities = set(pool.map(load_installation_id, [url] * 4))
    assert len(identities) == 1
    assert None not in identities


async def test_web_and_worker_share_identity_and_fresh_install_waits(tmp_path):
    from simple_module_hosting.config.installation import (
        ensure_installation_id,
        load_installation_id,
    )

    url = unmigrated_db_url(tmp_path)
    assert await ensure_installation_id(url) is None
    assert load_installation_id(url) is None
    seed_settings_db(tmp_path / "unmigrated.db", [])
    assert await ensure_installation_id(url) == load_installation_id(url)


async def test_lookup_failure_does_not_mint_a_process_local_identity():
    from simple_module_hosting.config.installation import ensure_installation_id

    with pytest.raises(OSError):
        await ensure_installation_id("postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing")
