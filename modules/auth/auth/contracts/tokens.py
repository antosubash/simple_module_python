"""Credential kinds and API-token prefixes shared by every auth source.

Lives in ``auth`` rather than in the ``api_tokens`` module because the auth
*providers* need it: ``users`` and ``keycloak`` both claim every
``Authorization: Bearer`` header, and must step aside for a value that is
recognisably an ``api_tokens`` credential — otherwise each token request costs
a wasted lookup against the provider's own token store (or a JWT parse), and
the provider's ``None`` there is final, so the principal resolver that
actually owns the token never gets to see it.
"""

from __future__ import annotations

AUTH_KIND_SESSION = "session"
"""A browser sign-in: the principal came from the session cookie."""

AUTH_KIND_BEARER = "bearer"
"""An auth provider's own ``Authorization: Bearer`` credential — a ``users``
access token or an identity provider's JWT. Unscoped (it carries its user's
full rights, as before), but not a person at a keyboard: it may not manage
API tokens, so a short-lived access token cannot mint a year-long PAT."""

AUTH_KIND_PAT = "pat"
"""A personal access token acting for its owner, capped by its scopes."""

AUTH_KIND_SERVICE = "service"
"""A service API key: no person behind it, roles and tenant fixed at creation."""

PAT_PREFIX = "smpat_"
SERVICE_KEY_PREFIX = "smsk_"
API_TOKEN_PREFIXES: tuple[str, ...] = (PAT_PREFIX, SERVICE_KEY_PREFIX)


def is_api_token(credential: str) -> bool:
    """Whether a bearer value is an ``api_tokens`` credential (by prefix only)."""
    return credential.startswith(API_TOKEN_PREFIXES)


__all__ = [
    "API_TOKEN_PREFIXES",
    "AUTH_KIND_BEARER",
    "AUTH_KIND_PAT",
    "AUTH_KIND_SERVICE",
    "AUTH_KIND_SESSION",
    "PAT_PREFIX",
    "SERVICE_KEY_PREFIX",
    "is_api_token",
]
