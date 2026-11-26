import os
from pathlib import Path

import pytest
from simple_module_remote.config.credentials import (
    CredentialError,
    CredentialStore,
    StoredCredential,
)

CLI = "smdev"
SECRET = "s3cr3t-token-value"
ORIGIN = "https://app.example.com"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_keyring) -> CredentialStore:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return CredentialStore(CLI, backend=fail_keyring)


def test_unreadable_file_says_delete(store: CredentialStore, monkeypatch) -> None:
    """A read error on credentials.toml keeps the corrupt-file recovery hint."""
    store.put("prod", StoredCredential(SECRET, ORIGIN))
    real_fdopen = os.fdopen

    class Failing:
        def __init__(self, fd: int, mode: str) -> None:
            self._handle = real_fdopen(fd, mode)

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            self._handle.close()

        def fileno(self) -> int:
            return self._handle.fileno()

        def read(self) -> bytes:
            raise OSError("EIO")

    monkeypatch.setattr("simple_module_remote.config._file_store.os.fdopen", Failing)
    with pytest.raises(CredentialError, match="delete it"):
        store.get("prod")
