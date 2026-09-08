"""What counts as a secret on a settings field, and how one is hidden.

Split out of ``_module_settings`` so the "should this value be shown?"
question — a name rule, a value rule and one mask — lives in one file and can
be reasoned about without a FastAPI app in scope. Re-exported from
``_module_settings``, which is where the rest of the codebase imports it from.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

# We intentionally DON'T match the bare word "token" (would mask
# `verification_token_lifetime_seconds` — just an int) or "key" alone (would
# mask `s3_bucket_key_prefix`). Only fragments that actually indicate material.
_SECRET_PATTERNS = re.compile(
    r"(password|secret|api[_-]?key|private[_-]?key|token[_-]?secret)", re.I
)
SECRET_MASK = "••••••••"

# Value types that cannot carry credential material, so a secret-ish *name*
# on one of them is a false positive rather than something to hide.
_NEVER_SECRET_TYPES = frozenset({"int", "float", "bool"})


def is_secret_field(name: str) -> bool:
    """True if a field name suggests it holds credential material."""
    return bool(_SECRET_PATTERNS.search(name))


def is_named_secret(name: str, value_type: str | None = None) -> bool:
    """True if the *name* marks this field as credential material.

    ``value_type`` exempts the types that cannot hold one, so a numeric field
    whose name merely contains a secret-ish word is not masked and made
    uneditable — ``reset_password_token_lifetime_seconds`` is an int, but it
    matches on "password" exactly as the real secrets do. Phrased as "exempt
    the types that cannot hold a credential" rather than "mask only strings" so
    the failure direction is safe: an unexpected type (``str | None`` resolves
    to "json") stays masked instead of silently exposing a secret.
    """
    if value_type in _NEVER_SECRET_TYPES:
        return False
    return is_secret_field(name)


def conceals_secret(name: str, value: Any, value_type: str | None = None) -> bool:
    """True if this name/value pair must be masked on the way out.

    The one rule every read path shares: mask per *value* as well as per name,
    so a DSN carrying a password is hidden even on a field called
    ``broker_url``, while that field's password-free default is still shown.
    """
    return is_named_secret(name, value_type) or embeds_credential(value)


def embeds_credential(value: Any) -> bool:
    """True if ``value`` carries a password in a URL authority.

    The name rule alone cannot see these: ``broker_url``, ``result_backend``,
    ``redis_url`` and ``database_url`` match nothing in
    :data:`_SECRET_PATTERNS`, yet a production DSN is precisely where the
    Redis and Postgres passwords live — and those fields are ``env_readable``,
    so the value reached both the module editor and the ``known_keys``
    suggestion list in clear text.

    Judged on the value rather than the name because the name is the thing
    that was wrong. A DSN without a password stays visible: hiding
    ``redis://localhost:6379/0`` helps nobody debug why the queue is idle.

    Containers are walked rather than dismissed: a ``list[str]`` of broker
    URLs or a ``dict`` of per-tenant DSNs holds exactly the same material as
    the bare string, and returning False for anything non-``str`` meant one
    such field would have been shown in full.
    """
    if isinstance(value, str):
        if "://" not in value:
            return False
        try:
            return bool(urlsplit(value).password)
        except ValueError:
            # A malformed authority (an unclosed IPv6 literal, say) is not a
            # credential, but it must not take the settings screen down either.
            return False
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(embeds_credential(item) for item in value)
    if isinstance(value, dict):
        return any(embeds_credential(item) for item in value.values())
    return False


def mask(value: Any) -> Any:
    if value in (None, "", [], {}):
        return value
    return SECRET_MASK
