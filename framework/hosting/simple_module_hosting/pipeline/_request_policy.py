"""Compile request-guard settings once per hydration, then share immutable values."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.web.cors import CorsPolicy
from simple_module_core.web.rate_limit import RateSpec, parse_rate
from starlette.types import Scope

from simple_module_hosting.config.host_settings import HostSettings


def host_policy(settings: HostSettings) -> CorsPolicy | None:
    """The host API policy; absent when no allowed origin is configured."""
    if not settings.cors_allow_origins:
        return None
    return CorsPolicy(
        origins=tuple(settings.cors_allow_origins),
        allow_credentials=settings.cors_allow_credentials,
        methods=tuple(settings.cors_allow_methods),
        headers=tuple(settings.cors_allow_headers),
        expose_headers=tuple(settings.cors_expose_headers),
        max_age=settings.cors_max_age,
    )


@dataclass(frozen=True, slots=True)
class RequestGuardPolicy:
    max_bytes: int
    public_rate: RateSpec | None
    authenticated_rate: RateSpec | None
    cors: CorsPolicy | None

    @classmethod
    def from_settings(cls, settings: HostSettings) -> RequestGuardPolicy:
        return cls(
            settings.max_request_body_bytes,
            parse_rate(settings.rate_limit_public),
            parse_rate(settings.rate_limit_authenticated),
            host_policy(settings),
        )


def request_policy(scope: Scope) -> RequestGuardPolicy | None:
    """Pin one snapshot across all guards, including a body still being streamed."""
    key = "sm.request_guard_policy"
    if key not in scope:
        host = getattr(getattr(scope.get("app"), "state", None), "host", None)
        scope[key] = getattr(host, "request_guards", None)
    return scope[key]
