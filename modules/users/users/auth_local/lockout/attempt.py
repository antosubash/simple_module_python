"""Normalised login attempt keys and admission results."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from simple_module_core.rate_limit import RateSpec, WindowStore

if TYPE_CHECKING:
    from users.settings import UsersSettings


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    """One password login: who, from where, against which store, and when."""

    username: str
    ip: str
    store: WindowStore
    settings: UsersSettings
    now: datetime

    @classmethod
    def build(
        cls,
        username: str,
        ip: str,
        store: WindowStore,
        settings: UsersSettings,
        now: datetime,
    ) -> LoginAttempt:
        # Normalised once, here: ``Alice@x `` and ``alice@x`` are one account
        # to the user lookup, so they must be one counter too.
        return cls(username.strip().lower(), ip, store, settings, now)

    @property
    def threshold(self) -> int:
        return self.settings.login_lockout_account_failures

    @property
    def cooldown(self) -> int:
        return self.settings.login_rate_limit_cooldown_seconds

    @property
    def key_name(self) -> str:
        """The username as it appears in store keys.

        The body limit is 10 MiB, so an unauthenticated caller could otherwise
        park a megabyte-long key in Redis per request. Anything longer than an
        address can be (254) is hashed; it matches no account either way.
        """
        if len(self.username) <= 254:
            return self.username
        return hashlib.sha256(self.username.encode()).hexdigest()

    @property
    def ip_key(self) -> str:
        return f"login:ip:{self.ip}:{self.key_name}"

    @property
    def ip_spec(self) -> RateSpec:
        s = self.settings
        return RateSpec(s.login_rate_limit_failures, s.login_rate_limit_window_seconds)

    @property
    def account_key(self) -> str:
        return f"login:acct:{self.key_name}"

    @property
    def lock_key(self) -> str:
        return f"login:acct-lock:{self.key_name}"

    @property
    def lock_spec(self) -> RateSpec:
        return RateSpec(1, self.cooldown)


@dataclass(frozen=True, slots=True)
class Admission:
    """A slot taken by :func:`admit`: the account rows it counted against and the count."""

    user_ids: tuple[uuid.UUID, ...]
    count: int
