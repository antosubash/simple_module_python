"""What a provider tells the callback about the person signing in (#877, #878)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from typing import Any

from users.core.oauth_settings import normalize_domain


@dataclass(frozen=True)
class OAuthIdentity:
    """One sign-in's identity: the link key, the email and its proof, and the profile.

    ``subject``, ``username``, ``display_name`` and ``extra`` are stored on the
    ``OAuthAccount`` link and refreshed on every sign-in; only ``display_name``
    reaches the account itself (``User.full_name``).
    """

    account_id: str
    email: str | None
    email_verified: bool
    subject: str | None = None
    username: str | None = None
    display_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def trusting(self, domains: Collection[str]) -> OAuthIdentity:
        """This identity with its email verified when it sits on one of ``domains``."""
        if self.email_verified or not email_on_domains(self.email, domains):
            return self
        return replace(self, email_verified=True)


def email_on_domains(email: str | None, domains: Collection[str]) -> bool:
    """Whether ``email``'s domain is exactly one of ``domains`` (no subdomains)."""
    if not email or not domains or email.count("@") != 1:
        return False
    try:
        return normalize_domain(email.rsplit("@", 1)[1]) in domains
    except ValueError:
        return False
