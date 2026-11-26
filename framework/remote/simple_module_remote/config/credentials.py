"""Credentials bound to the server origin they were issued for."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import keyring
import keyring.backends.fail
import keyring.errors

from simple_module_remote.config._file_store import (
    ORIGIN_FIELD,
    PIN_FIELDS,
    TOKEN_FIELD,
    FileStore,
    FileStoreError,
)
from simple_module_remote.config.environments import Environment
from simple_module_remote.config.paths import env_prefix, env_var_name

TOKEN_ENV_SUFFIX = "_TOKEN"
MASK = "***"
# Keyring backends cannot enumerate, so the keys stored are tracked under this name;
# environment names are [a-z0-9-], so it never collides with a credential key.
INDEX_KEY = "~index"


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
    # The tenant the token was pinned to when it was stored (from whoami at login).
    tenant_id: str | None = None
    tenant_slug: str | None = None

    def __repr__(self) -> str:
        return f"StoredCredential(token={MASK!r}, origin={self.origin!r})"

    def pins(self) -> dict[str, str]:
        found = {"tenant_id": self.tenant_id, "tenant_slug": self.tenant_slug}
        return {k: v for k, v in found.items() if v is not None}


def validate_token(token: str, *, source: str) -> str:
    """``token`` when it is printable ASCII without whitespace; never echoes the value."""
    if not token or not all(0x21 <= ord(ch) <= 0x7E for ch in token):
        raise CredentialError(
            f"{source} is not a valid token: it must be printable ASCII with no spaces or "
            "control characters"
        )
    return token


def describe_tenant(slug: object, tenant_id: object) -> str:
    """``slug (id)`` for a tenant, or just the id when no slug is known."""
    if slug and tenant_id:
        return f"{slug} ({tenant_id})"
    return str(slug or tenant_id or "none")


SINGLE_TENANT_ID = "default"  # what a single-tenant server reports as the tenant id


def is_single_tenant(who: Mapping[str, object]) -> bool:
    """Whether whoami describes a single-tenant server (no real tenant to select)."""
    return who.get("tenant_id") == SINGLE_TENANT_ID and not who.get("tenant_slug")


def tenant_matches(wanted: str, who: Mapping[str, object]) -> bool:
    """Whether ``wanted`` (a slug or an id) names the tenant a token is pinned to."""
    return wanted in (who.get("tenant_id"), who.get("tenant_slug"))


def credential_key(env: str, tenant: str | None) -> str:
    return f"{env}/{tenant}" if tenant else env


def _keyring_usable() -> bool:
    backend = keyring.get_keyring()
    if isinstance(backend, keyring.backends.fail.Keyring):
        return False
    return getattr(backend, "priority", 0) >= 1


def _pin_kwargs(data: Mapping[str, object]) -> dict[str, str | None]:
    return {f: v if isinstance(v := data.get(f), str) else None for f in PIN_FIELDS}


class CredentialStore:
    def __init__(self, cli: str, *, backend: KeyringBackend | None = None) -> None:
        self._service = cli
        self._file: FileStore | None = None
        self._backend: KeyringBackend | None = None
        if backend is None:
            if _keyring_usable():
                self._backend = keyring.get_keyring()
        elif not isinstance(backend, keyring.backends.fail.Keyring):
            self._backend = backend

    @property
    def using_fallback(self) -> bool:
        return self._backend is None

    def _file_store(self) -> FileStore | None:
        """The fallback file store, built on first use (raises FileStoreError if unsupported)."""
        if self._backend is not None:
            return None
        if self._file is None:
            self._file = FileStore(self._service)
        return self._file

    def _require_backend(self) -> KeyringBackend:
        if self._backend is None:
            raise CredentialError("no credential backend is available")
        return self._backend

    def get(self, key: str) -> StoredCredential | None:
        try:
            if (file := self._file_store()) is not None:
                found = file.get(key)
                if not found:
                    return None
                return StoredCredential(
                    found[TOKEN_FIELD], found[ORIGIN_FIELD], **_pin_kwargs(found)
                )
            return self._keyring_get(key)
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be read") from None

    def _keyring_get(self, key: str) -> StoredCredential | None:
        raw = self._require_backend().get_password(self._service, key)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            token, origin = data[TOKEN_FIELD], data[ORIGIN_FIELD]
        except (ValueError, KeyError, TypeError):
            raise CredentialError(f"stored credential {key!r} is corrupt; log in again") from None
        if not isinstance(token, str) or not isinstance(origin, str):
            raise CredentialError(f"stored credential {key!r} is corrupt; log in again")
        return StoredCredential(token=token, origin=origin, **_pin_kwargs(data))

    def _index(self) -> list[str]:
        raw = self._require_backend().get_password(self._service, INDEX_KEY)
        try:
            data = json.loads(raw) if raw else []
        except ValueError:
            return []
        return [k for k in data if isinstance(k, str)] if isinstance(data, list) else []

    def _set_index(self, keys: list[str]) -> None:
        backend = self._require_backend()
        if keys:
            backend.set_password(self._service, INDEX_KEY, json.dumps(sorted(keys)))
        elif backend.get_password(self._service, INDEX_KEY) is not None:
            backend.delete_password(self._service, INDEX_KEY)

    def put(self, key: str, cred: StoredCredential) -> None:
        try:
            if (file := self._file_store()) is not None:
                file.put(key, cred.token, cred.origin, cred.pins())
            else:
                payload = json.dumps(
                    {TOKEN_FIELD: cred.token, ORIGIN_FIELD: cred.origin, **cred.pins()}
                )
                backend = self._require_backend()
                backend.set_password(self._service, key, payload)
                known = self._index()
                if key not in known:
                    self._set_index([*known, key])
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be written") from None

    def delete_env(self, env: str) -> list[str]:
        """Delete every credential of ``env`` (``env`` and ``env/<tenant>``); the keys removed."""
        try:
            if (file := self._file_store()) is not None:
                candidates = file.keys()
            else:
                candidates = [env, *self._index()]
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be read") from None
        wanted = [k for k in dict.fromkeys(candidates) if k == env or k.startswith(env + "/")]
        return [key for key in wanted if self.delete(key)]

    def delete(self, key: str) -> bool:
        try:
            if (file := self._file_store()) is not None:
                return file.delete(key)
            backend = self._require_backend()
            known = self._index()
            if key in known:
                self._set_index([k for k in known if k != key])
            if backend.get_password(self._service, key) is None:
                return False
            backend.delete_password(self._service, key)
            return True
        except FileStoreError as exc:
            raise CredentialError(str(exc)) from None
        except keyring.errors.PasswordDeleteError:
            return False
        except keyring.errors.KeyringError:
            raise CredentialError("the OS keyring could not be updated") from None


def token_env_var(cli: str) -> str:
    """The environment variable that supplies a token for *cli*."""
    return env_prefix(cli) + TOKEN_ENV_SUFFIX


def login_hint(cli: str, env: Environment, tenant: str | None) -> str:
    """The command that stores a token; root options (--env, --tenant) precede the subcommand."""
    hint = f"{cli} --env {env.name}"
    hint = f"{hint} --tenant {tenant}" if tenant else hint
    return f"{hint} login --token"


def resolve_token(
    store: CredentialStore,
    env: Environment,
    tenant: str | None,
    environ: Mapping[str, str],
    cli: str,
    explicit: bool,
) -> str:
    var = token_env_var(cli)
    from_env = environ.get(var)
    if from_env:
        if explicit:
            return validate_token(from_env, source=var)
        raise CredentialError(
            f"{var} is set but not used: it is only honoured when the environment is chosen "
            f"explicitly (pass --env or set {env_var_name(cli)})"
        )
    cred = store.get(credential_key(env.name, tenant))
    hint = login_hint(cli, env, tenant)
    if cred is None:
        raise CredentialError(f"no stored credentials for {env.name!r}: run `{hint}`")
    if cred.origin != env.origin:
        raise CredentialError(
            f"the stored token for {env.name!r} was issued for {cred.origin}, "
            f"but the environment now points at {env.origin}: run `{hint}`"
        )
    pinned = {"tenant_id": cred.tenant_id, "tenant_slug": cred.tenant_slug}
    if (
        tenant
        and cred.tenant_id is not None
        and not is_single_tenant(pinned)
        and tenant not in (cred.tenant_id, cred.tenant_slug)
    ):
        raise CredentialError(
            f"the stored token for {credential_key(env.name, tenant)!r} is pinned to tenant "
            f"{describe_tenant(cred.tenant_slug, cred.tenant_id)}, not {tenant!r}: run `{hint}`"
        )
    return cred.token
