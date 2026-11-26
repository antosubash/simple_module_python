"""Credentials bound to the server origin they were issued for."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import keyring
import keyring.backends.fail
import keyring.errors

from simple_module_remote.config._file_store import FileStore, FileStoreError
from simple_module_remote.config.environments import Environment
from simple_module_remote.config.paths import env_prefix

TOKEN_ENV_SUFFIX = "_TOKEN"
TOKEN_KEY = "token"
ORIGIN_KEY = "origin"
MASK = "***"


class CredentialError(Exception):
    """Raised for missing or unusable credentials; the message never contains a token."""


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str, /) -> str | None: ...
    def set_password(self, service: str, username: str, password: str, /) -> None: ...
    def delete_password(self, service: str, username: str, /) -> None: ...


@dataclass(frozen=True, repr=False)
class StoredCredential:
    token: str
    origin: str

    def __repr__(self) -> str:
        return f"StoredCredential(token={MASK!r}, origin={self.origin!r})"


def credential_key(env: str, tenant: str | None) -> str:
    return f"{env}/{tenant}" if tenant else env


def _keyring_usable() -> bool:
    backend = keyring.get_keyring()
    if isinstance(backend, keyring.backends.fail.Keyring):
        return False
    return getattr(backend, "priority", 0) >= 1


class CredentialStore:
    def __init__(self, cli: str, *, backend: KeyringBackend | None = None) -> None:
        self._service = cli
        self._file: FileStore | None = None
        self._backend: KeyringBackend | None = None
        if backend is None:
            if _keyring_usable():
                self._backend = keyring.get_keyring()
        elif isinstance(backend, keyring.backends.fail.Keyring):
            pass
        else:
            self._backend = backend
        if self._backend is None:
            self._file = FileStore(cli)

    @property
    def using_fallback(self) -> bool:
        return self._file is not None

    def get(self, key: str) -> StoredCredential | None:
        try:
            if self._file is not None:
                found = self._file.get(key)
                return StoredCredential(*found) if found else None
            return self._keyring_get(key)
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be read") from None

    def _keyring_get(self, key: str) -> StoredCredential | None:
        assert self._backend is not None
        raw = self._backend.get_password(self._service, key)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            token, origin = data[TOKEN_KEY], data[ORIGIN_KEY]
        except (ValueError, KeyError, TypeError):
            raise CredentialError(f"stored credential {key!r} is corrupt; log in again") from None
        if not isinstance(token, str) or not isinstance(origin, str):
            raise CredentialError(f"stored credential {key!r} is corrupt; log in again")
        return StoredCredential(token=token, origin=origin)

    def put(self, key: str, cred: StoredCredential) -> None:
        try:
            if self._file is not None:
                self._file.put(key, cred.token, cred.origin)
            else:
                assert self._backend is not None
                payload = json.dumps({TOKEN_KEY: cred.token, ORIGIN_KEY: cred.origin})
                self._backend.set_password(self._service, key, payload)
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be written") from None

    def delete(self, key: str) -> bool:
        try:
            if self._file is not None:
                return self._file.delete(key)
            assert self._backend is not None
            if self._backend.get_password(self._service, key) is None:
                return False
            self._backend.delete_password(self._service, key)
            return True
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.PasswordDeleteError:
            return False
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be updated") from None


def _login_hint(cli: str, env: Environment, tenant: str | None) -> str:
    hint = f"{cli} login --env {env.name}"
    return f"{hint} --tenant {tenant}" if tenant else hint


def resolve_token(
    store: CredentialStore,
    env: Environment,
    tenant: str | None,
    environ: Mapping[str, str],
    cli: str,
    explicit: bool,
) -> str:
    var = env_prefix(cli) + TOKEN_ENV_SUFFIX
    from_env = environ.get(var)
    if from_env:
        if explicit:
            return from_env
        raise CredentialError(
            f"{var} is set but ignored: it is only honoured when the environment is chosen "
            f"explicitly (pass --env or set {env_prefix(cli)}_ENV)"
        )
    cred = store.get(credential_key(env.name, tenant))
    hint = _login_hint(cli, env, tenant)
    if cred is None:
        raise CredentialError(f"no stored credentials for {env.name!r}: run `{hint}`")
    if cred.origin != env.origin:
        raise CredentialError(
            f"the stored token for {env.name!r} was issued for {cred.origin}, "
            f"but the environment now points at {env.origin}: run `{hint}`"
        )
    return cred.token
