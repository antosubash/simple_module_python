"""Runtime token keys; legacy env overrides expire in 0.0.50 (#969)."""

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from simple_module_core.runtime.crypto import derive_key
from simple_module_core.runtime.deprecation import deprecate
from simple_module_core.settings.dotenv import env_str

logger = logging.getLogger(__name__)

_LEGACY = {
    name: deprecate(name, remove_in="0.0.50", use="keys derived from the host root secret")
    for name in (
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
        "SM_USERS_VERIFICATION_TOKEN_SECRET",
    )
}


@dataclass(frozen=True)
class TokenSecrets:
    reset_password_token_secret: str
    verification_token_secret: str


def _resolve(root: str, env: str, placeholder: str, label: bytes) -> str:
    value = env_str(env, "")
    if value and value != placeholder:
        logger.warning(_LEGACY[env].message)
        return value
    return base64.urlsafe_b64encode(derive_key(root, label)).decode()


def resolve_token_secrets(root: str) -> TokenSecrets:
    """Derive purpose-specific keys, preserving explicit legacy overrides."""
    return TokenSecrets(
        reset_password_token_secret=_resolve(
            root,
            "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
            "dev-reset-token-secret-change-me",
            b"simple-module/v1/users/password-reset",
        ),
        verification_token_secret=_resolve(
            root,
            "SM_USERS_VERIFICATION_TOKEN_SECRET",
            "dev-verify-token-secret-change-me",
            b"simple-module/v1/users/email-verification",
        ),
    )


class RuntimeTokenSecrets:
    """Follow the current host root, including its first-run persistence swap."""

    def __init__(self, root: Callable[[], str]) -> None:
        self._root = root
        self._resolve = lru_cache(maxsize=1)(resolve_token_secrets)
        self._resolve(root())  # Emit legacy-override warnings during registration.

    @property
    def reset_password_token_secret(self) -> str:
        return self._resolve(self._root()).reset_password_token_secret

    @property
    def verification_token_secret(self) -> str:
        return self._resolve(self._root()).verification_token_secret


class TokenSecretsMixin:
    """Managers read signing keys when used, rather than capturing them at init."""

    _token_secrets: TokenSecrets | RuntimeTokenSecrets

    @property
    def reset_password_token_secret(self) -> str:
        return self._token_secrets.reset_password_token_secret

    @property
    def verification_token_secret(self) -> str:
        return self._token_secrets.verification_token_secret
