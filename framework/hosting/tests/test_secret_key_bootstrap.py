"""SM_SECRET_KEY becomes optional: env → DB → generate and persist.

The concurrency test is the point of this file. Several uvicorn workers boot
at once against the same empty database; if each minted its own key they would
continuously invalidate each other's sessions, and the symptom — users
randomly logged out, only under multiple workers — is miserable to trace back
to here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from _hosting_settings_db import seed_settings_db, unmigrated_db_url
from simple_module_hosting._secret_key import ensure_secret_key


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    return seed_settings_db(tmp_path / "secret.db", [])


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SM_SECRET_KEY", raising=False)


def test_generates_a_strong_key(fresh_db_url: str) -> None:
    key = ensure_secret_key(fresh_db_url)
    assert len(key) >= 40


def test_key_is_stable_across_boots(fresh_db_url: str) -> None:
    """Restarting the process must not log everyone out."""
    assert ensure_secret_key(fresh_db_url) == ensure_secret_key(fresh_db_url)


def test_concurrent_boots_converge_on_one_key(fresh_db_url: str) -> None:
    """Several workers booting together must agree, or they invalidate each
    other's sessions intermittently."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = set(pool.map(lambda _: ensure_secret_key(fresh_db_url), range(8)))

    assert len(keys) == 1, f"workers minted {len(keys)} different keys"


def test_env_wins(monkeypatch: pytest.MonkeyPatch, fresh_db_url: str) -> None:
    monkeypatch.setenv("SM_SECRET_KEY", "explicit-key-from-environment")
    assert ensure_secret_key(fresh_db_url) == "explicit-key-from-environment"


def test_env_value_is_not_persisted(monkeypatch: pytest.MonkeyPatch, fresh_db_url: str) -> None:
    """Writing the env key into the DB would leave a stale copy that outlives
    a deliberate rotation of the env var."""
    monkeypatch.setenv("SM_SECRET_KEY", "explicit-key-from-environment")
    ensure_secret_key(fresh_db_url)

    monkeypatch.delenv("SM_SECRET_KEY")
    generated = ensure_secret_key(fresh_db_url)

    assert generated != "explicit-key-from-environment"


def test_unreachable_db_still_returns_a_key() -> None:
    """A key is needed to build the app at all, and the setup wizard cannot
    report an unreachable DB if the process never starts."""
    key = ensure_secret_key("postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing")
    assert len(key) >= 40


def test_unmigrated_db_still_returns_a_key(tmp_path: Path) -> None:
    assert len(ensure_secret_key(unmigrated_db_url(tmp_path))) >= 40
