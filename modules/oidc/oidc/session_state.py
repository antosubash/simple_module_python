"""Whether the browser session already holds an OIDC sign-in."""

from typing import Any

from oidc.constants import SESSION_USER_KEY


def is_signed_in(session: Any) -> bool:
    return isinstance(session.get(SESSION_USER_KEY), dict)
