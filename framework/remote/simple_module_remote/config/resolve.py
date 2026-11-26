"""Pick the credential a request uses: the environment variable or a stored login."""

from collections.abc import Mapping
from typing import NamedTuple

from simple_module_remote.config.credentials import (
    CredentialError,
    CredentialStore,
    StoredCredential,
    credential_key,
    describe_tenant,
    is_single_tenant,
    login_hint,
    tenant_matches,
    token_env_var,
    validate_token,
)
from simple_module_remote.config.environments import Environment
from simple_module_remote.config.paths import env_var_name
from simple_module_remote.http.safety import normalize_origin

__all__ = ["ResolvedToken", "find_credential", "resolve_credential", "resolve_token"]


class ResolvedToken(NamedTuple):
    token: str
    # How to name the tenant in output: the slug when the stored login knows it.
    tenant_label: str | None


def find_credential(
    store: CredentialStore, env: Environment, tenant: str | None
) -> tuple[str, StoredCredential] | None:
    """The stored login for ``env``/``tenant``, as ``(key, credential)``.

    A single-tenant server ignores ``--tenant``, so its login lives in the plain
    environment slot and is found from there when the tenant slot is empty.
    """
    key = credential_key(env.name, tenant)
    cred = store.get(key)
    if cred is not None:
        return key, cred
    if tenant:
        plain = store.get(env.name)
        if plain is not None and is_single_tenant(plain.pins()):
            return env.name, plain
    return None


def resolve_credential(
    store: CredentialStore,
    env: Environment,
    tenant: str | None,
    environ: Mapping[str, str],
    cli: str,
    explicit: bool,
) -> ResolvedToken:
    var = token_env_var(cli)
    from_env = environ.get(var)
    if from_env:
        if explicit:
            return ResolvedToken(validate_token(from_env, source=var), tenant)
        raise CredentialError(
            f"{var} is set but not used: it is only honoured when the environment is chosen "
            f"explicitly (pass --env or set {env_var_name(cli)})"
        )
    found = find_credential(store, env, tenant)
    hint = login_hint(cli, env, tenant)
    if found is None:
        raise CredentialError(f"no stored credentials for {env.name!r}: run `{hint}`")
    key, cred = found
    if normalize_origin(cred.origin) != env.origin:  # tolerates pre-normalisation logins
        raise CredentialError(
            f"the stored token for {env.name!r} was issued for {cred.origin}, "
            f"but the environment now points at {env.origin}: run `{hint}`"
        )
    pinned = cred.pins()
    single = is_single_tenant(pinned)
    if tenant and cred.tenant_id is not None and not single and not tenant_matches(tenant, pinned):
        raise CredentialError(
            f"the stored token for {key!r} is pinned to tenant "
            f"{describe_tenant(cred.tenant_slug, cred.tenant_id)}, not {tenant!r}: run `{hint}`"
        )
    label = None if single else (cred.tenant_slug or tenant)
    return ResolvedToken(cred.token, label)


def resolve_token(
    store: CredentialStore,
    env: Environment,
    tenant: str | None,
    environ: Mapping[str, str],
    cli: str,
    explicit: bool,
) -> str:
    return resolve_credential(store, env, tenant, environ, cli, explicit).token
