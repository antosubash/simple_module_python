"""Token format, generation and hashing — no I/O.

A token is ``<kind prefix><secret>``: ``smpat_`` for a personal access token,
``smsk_`` for a service key, then 32 bytes from :func:`secrets.token_bytes`
in base62, left-padded to a fixed width. Only ``sha256(token)`` is stored.

SHA-256 rather than a slow password hash is deliberate: the input carries 256
bits of entropy, so there is nothing to brute-force, and the hash is computed
on every authenticated request.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import NamedTuple

from auth.contracts.tokens import API_TOKEN_PREFIXES

from api_tokens.constants import (
    DISPLAY_PREFIX_LENGTH,
    KIND_PREFIX,
    SECRET_BYTES,
    SECRET_LENGTH,
    TokenKind,
)

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_FORMAT = re.compile(
    "^(?:"
    + "|".join(re.escape(p) for p in API_TOKEN_PREFIXES)
    + f")[0-9A-Za-z]{{{SECRET_LENGTH}}}$"
)


class NewToken(NamedTuple):
    """A freshly minted token. ``plaintext`` must reach the caller exactly once."""

    plaintext: str
    token_hash: str
    prefix: str


def base62(data: bytes) -> str:
    """Encode *data* in base62, left-padded with ``0`` to :data:`SECRET_LENGTH`."""
    number = int.from_bytes(data, "big")
    out: list[str] = []
    while number:
        number, rem = divmod(number, 62)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out)).rjust(SECRET_LENGTH, _ALPHABET[0])


def hash_token(plaintext: str) -> str:
    """The stored form of a token: lowercase hex SHA-256 of the whole string."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def is_well_formed(candidate: str) -> bool:
    """Whether *candidate* has the exact shape of a token we could have issued.

    Checked before any database read, so junk in an ``Authorization`` header
    costs a regex match and nothing else.
    """
    return _FORMAT.fullmatch(candidate) is not None


def display_prefix(plaintext: str) -> str:
    """The non-secret slice shown in lists: the kind prefix plus 8 characters."""
    for prefix in API_TOKEN_PREFIXES:
        if plaintext.startswith(prefix):
            return plaintext[: len(prefix) + DISPLAY_PREFIX_LENGTH]
    raise ValueError("not an API token")


def generate(kind: TokenKind) -> NewToken:
    """Mint a token of *kind*."""
    plaintext = KIND_PREFIX[kind] + base62(secrets.token_bytes(SECRET_BYTES))
    return NewToken(plaintext, hash_token(plaintext), display_prefix(plaintext))


__all__ = ["NewToken", "base62", "display_prefix", "generate", "hash_token", "is_well_formed"]
