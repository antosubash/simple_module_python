import fcntl
import importlib
import os
import stat
import sys
import threading
from pathlib import Path

import keyring.backends.fail
import keyring.errors
import pytest
from simple_module_remote.config._file_store import FileStore
from simple_module_remote.config.credentials import (
    CredentialError,
    CredentialStore,
    StoredCredential,
    credential_key,
    resolve_token,
)
from simple_module_remote.config.environments import Environment

CLI = "smdev"
SECRET = "s3cr3t-token-value"
ENV = Environment(name="prod", url="https://app.example.com/base")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_keyring) -> CredentialStore:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return CredentialStore(CLI, backend=fail_keyring)


def test_credential_key() -> None:
    assert credential_key("prod", None) == "prod"
    assert credential_key("prod", "acme") == "prod/acme"


def test_put_get_roundtrip_fallback(store: CredentialStore) -> None:
    assert store.using_fallback
    assert store.get("prod/acme") is None
    store.put("prod/acme", StoredCredential(SECRET, ENV.origin))
    assert store.get("prod/acme") == StoredCredential(SECRET, ENV.origin)
    assert store.delete("prod/acme") is True
    assert store.delete("prod/acme") is False
    assert store.get("prod/acme") is None


def test_fallback_file_mode_0600_dir_0700(store: CredentialStore, tmp_path: Path) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    path = tmp_path / CLI / "credentials.toml"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert sorted(p.name for p in path.parent.iterdir()) == [
        "credentials.toml",
        "credentials.toml.lock",
    ]
    assert stat.S_IMODE((path.parent / "credentials.toml.lock").stat().st_mode) == 0o600


def test_fallback_refuses_loose_permissions(store: CredentialStore, tmp_path: Path) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    (tmp_path / CLI / "credentials.toml").chmod(0o644)
    with pytest.raises(CredentialError) as err:
        store.get("prod")
    assert SECRET not in str(err.value)


def test_corrupt_file_error_has_no_token(store: CredentialStore, tmp_path: Path) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    (tmp_path / CLI / "credentials.toml").write_text(f"token = {SECRET}\n[", encoding="utf-8")
    with pytest.raises(CredentialError) as err:
        store.get("prod")
    assert SECRET not in str(err.value)


def test_keyring_path_stores_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keyring_store
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    fake = keyring_store
    store = CredentialStore(CLI, backend=fake)
    assert not store.using_fallback
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    assert fake.data[(CLI, "prod")] == f'{{"token": "{SECRET}", "origin": "{ENV.origin}"}}'
    assert store.get("prod") == StoredCredential(SECRET, ENV.origin)
    assert store.delete("prod") is True
    assert store.delete("prod") is False
    assert not (tmp_path / CLI).exists()


def test_origin_mismatch_refuses(store: CredentialStore) -> None:
    store.put("prod", StoredCredential(SECRET, "https://old.example.com"))
    with pytest.raises(CredentialError) as err:
        resolve_token(store, ENV, None, {}, CLI, explicit=False)
    assert "smdev --env prod login" in str(err.value)
    assert SECRET not in str(err.value)


def test_matching_origin_returns_token(store: CredentialStore) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    assert resolve_token(store, ENV, None, {}, CLI, explicit=False) == SECRET


def test_env_token_requires_explicit_env(store: CredentialStore) -> None:
    with pytest.raises(CredentialError) as err:
        resolve_token(store, ENV, None, {"SMDEV_TOKEN": SECRET}, CLI, explicit=False)
    assert "SMDEV_TOKEN" in str(err.value)
    assert "--env" in str(err.value)
    assert SECRET not in str(err.value)


def test_env_token_used_when_explicit(store: CredentialStore) -> None:
    assert resolve_token(store, ENV, None, {"SMDEV_TOKEN": SECRET}, CLI, explicit=True) == SECRET


def test_env_prefix_for_dashed_cli(store: CredentialStore) -> None:
    environ = {"MY_CLI_TOKEN": SECRET}
    assert resolve_token(store, ENV, None, environ, "my-cli", explicit=True) == SECRET


def test_missing_names_login_command(store: CredentialStore) -> None:
    with pytest.raises(CredentialError) as err:
        resolve_token(store, ENV, "acme", {}, CLI, explicit=False)
    assert "smdev --env prod --tenant acme login --token" in str(err.value)
    with pytest.raises(CredentialError) as err2:
        resolve_token(store, ENV, None, {}, CLI, explicit=False)
    assert "smdev --env prod login --token`" in str(err2.value)
    assert "--tenant" not in str(err2.value)


def test_repr_never_contains_token() -> None:
    cred = StoredCredential(SECRET, ENV.origin)
    assert SECRET not in repr(cred)
    assert SECRET not in str(cred)
    assert SECRET not in f"{cred!r}"


def test_existing_loose_dir_is_tightened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_keyring
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / CLI).mkdir(mode=0o755)
    (tmp_path / CLI).chmod(0o755)
    store = CredentialStore(CLI, backend=fail_keyring)
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    assert stat.S_IMODE((tmp_path / CLI).stat().st_mode) == 0o700


def test_symlink_credentials_refused(store: CredentialStore, tmp_path: Path) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    real = tmp_path / CLI / "credentials.toml"
    other = tmp_path / "other.toml"
    real.rename(other)
    real.symlink_to(other)
    with pytest.raises(CredentialError) as err:
        store.get("prod")
    assert "symlink" in str(err.value)
    assert SECRET not in str(err.value)


def test_foreign_owner_refused(store: CredentialStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    monkeypatch.setattr("simple_module_remote.config._file_store.os.getuid", lambda: 12345)
    with pytest.raises(CredentialError) as err:
        store.get("prod")
    assert "another user" in str(err.value)


def test_corrupt_file_says_delete(store: CredentialStore, tmp_path: Path) -> None:
    store.put("prod", StoredCredential(SECRET, ENV.origin))
    (tmp_path / CLI / "credentials.toml").write_text("[", encoding="utf-8")
    with pytest.raises(CredentialError, match="delete it"):
        store.get("prod")


class BrokenKeyring:
    def get_password(self, service_name: str, username: str) -> str | None:
        raise keyring.errors.KeyringError(SECRET)

    def set_password(self, service_name: str, username: str, password: str) -> None:
        raise keyring.errors.KeyringError(SECRET)

    def delete_password(self, service_name: str, username: str) -> None:
        raise keyring.errors.KeyringError(SECRET)


def test_keyring_errors_map_to_credential_error() -> None:
    store = CredentialStore(CLI, backend=BrokenKeyring())
    with pytest.raises(CredentialError) as err:
        store.get("prod")
    assert SECRET not in str(err.value)
    with pytest.raises(CredentialError):
        store.put("prod", StoredCredential(SECRET, ENV.origin))
    with pytest.raises(CredentialError):
        store.delete("prod")


def test_readonly_credential_dir_is_clean_error(tmp_path, fail_keyring):
    from simple_module_remote.config.credentials import (
        CredentialError,
        CredentialStore,
        StoredCredential,
    )

    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    directory = tmp_path / "config" / "smdev"
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o500)
    store = CredentialStore("smdev", backend=fail_keyring)
    try:
        with pytest.raises(CredentialError) as err:
            store.put("k", StoredCredential("tok-secret", "https://x"))
    finally:
        directory.chmod(0o700)
    assert "PermissionError" in str(err.value) and "tok-secret" not in str(err.value)


def test_fallback_updates_hold_an_exclusive_lock(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = {"locked": False}
    real_flock = fcntl.flock
    real_load = FileStore._load

    def flock(fd: int, op: int) -> None:
        real_flock(fd, op)
        held["locked"] = op == fcntl.LOCK_EX

    def load(self):
        assert held["locked"], "read-modify-write ran without the cross-process lock"
        return real_load(self)

    monkeypatch.setattr(fcntl, "flock", flock)
    monkeypatch.setattr(FileStore, "_load", load)
    store.put("a", StoredCredential(SECRET, ENV.origin))
    assert store.delete("a") is True
    assert store.delete("a") is False


def test_fallback_update_waits_for_another_holder(store: CredentialStore, tmp_path: Path) -> None:
    store.put("a", StoredCredential(SECRET, ENV.origin))
    lock_path = tmp_path / CLI / "credentials.toml.lock"
    fd = os.open(lock_path, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    done = threading.Event()

    def writer() -> None:
        store.put("b", StoredCredential(SECRET, ENV.origin))
        done.set()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert not done.wait(timeout=0.3)
    finally:
        os.close(fd)
    thread.join(timeout=5)
    assert done.is_set() and store.get("b") is not None


def test_fallback_store_works_without_fcntl(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "fcntl", None)  # `import fcntl` now raises ImportError
    importlib.reload(importlib.import_module("simple_module_remote.config._file_store"))
    store.put("a", StoredCredential(SECRET, ENV.origin))
    assert store.get("a") == StoredCredential(SECRET, ENV.origin)
