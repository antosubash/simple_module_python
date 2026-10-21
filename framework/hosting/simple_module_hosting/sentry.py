"""Optional Sentry error reporting (#538).

``init_sentry`` is the only entry point. With ``SM_SENTRY_DSN`` unset it
returns before importing ``sentry_sdk``, so the ``sentry`` extra stays
optional and costs nothing. The DSN is a secret and process wiring that must
be known before the DB opens, hence env only; it is never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from typing import Any, Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.correlation import correlation_id
from simple_module_db.listeners import current_user_id
from simple_module_db.tenancy import current_tenant_id
from starlette.types import ASGIApp, Receive, Scope, Send

from simple_module_hosting.sentry_scrub import scrub_event

logger = logging.getLogger(__name__)

Process = Literal["web", "worker"]
PROCESS_WEB: Process = "web"
PROCESS_WORKER: Process = "worker"

_TAG_REQUEST_ID = "request_id"
_TAG_TENANT = "tenant"
_TAG_USER_ID = "user_id"
_TAG_MODULE = "module"
_TAG_TASK = "task"
_TAG_PROCESS = "process"
_TASK_SEP = "."

Event = dict[str, Any]

# The ASGI scope of the request in flight. Tenant/auth ContextVars are reset
# by their middleware before an unhandled error reaches Sentry's capture point
# (outside the whole stack), but ``scope["state"]`` and ``scope["endpoint"]``
# survive, so the processor reads those first.
_request_scope: ContextVar[Scope | None] = ContextVar("sentry_request_scope", default=None)
_enabled = False


def is_enabled() -> bool:
    return _enabled


class SentryContextMiddleware:
    """Expose the request scope to the Sentry event processor."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            _request_scope.set(scope)
        await self.app(scope, receive, send)


class SentrySettings(BaseSettings):
    """Env-only Sentry wiring (``SM_SENTRY_*``)."""

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    sentry_dsn: SecretStr | None = None
    sentry_environment: str | None = None
    sentry_traces_sample_rate: float = 0.0
    environment: str = "development"


def _scope_info(process: Process) -> dict[str, str | None]:
    scope = _request_scope.get() if process == PROCESS_WEB else None
    state = (scope or {}).get("state", {})
    user = state.get("user")
    endpoint = (scope or {}).get("endpoint")
    return {
        _TAG_TENANT: state.get("tenant_id"),
        _TAG_REQUEST_ID: state.get("correlation_id"),
        _TAG_USER_ID: getattr(user, "id", None),
        _TAG_MODULE: getattr(endpoint, "__module__", "").split(_TASK_SEP, 1)[0] or None,
    }


def _tags(event: Event, process: Process) -> dict[str, str]:
    info = _scope_info(process)
    info[_TAG_TENANT] = info[_TAG_TENANT] or current_tenant_id.get()
    info[_TAG_REQUEST_ID] = info[_TAG_REQUEST_ID] or correlation_id.get()
    info[_TAG_USER_ID] = info[_TAG_USER_ID] or current_user_id.get()
    # Fallback: events are named after the endpoint ("<pkg>.endpoints.api.fn")
    # or the task ("<module>.<task>"); both lead with the module.
    transaction = event.get("transaction")
    if not info[_TAG_MODULE] and isinstance(transaction, str) and _TASK_SEP in transaction:
        info[_TAG_MODULE] = transaction.split(_TASK_SEP, 1)[0]
    if process == PROCESS_WORKER and isinstance(transaction, str):
        info[_TAG_TASK] = transaction
    info[_TAG_PROCESS] = process
    return {k: str(v) for k, v in info.items() if v}


def build_before_send(process: Process) -> Callable[[Event, Mapping[str, Any]], Event]:
    """Tag and scrub an event; used for errors and transactions alike.

    Scrubbing is ours, not the SDK's: its ``EventScrubber`` matches exact key
    names only and skips ``contexts`` and free text (``sentry_scrub``).
    """

    def before_send(event: Event, hint: Mapping[str, Any]) -> Event:
        tags = _tags(event, process)
        event.setdefault("tags", {}).update(tags)
        if user_id := tags.get(_TAG_USER_ID):
            event["user"] = {"id": user_id}  # id only: never email/username/ip
        else:
            event.pop("user", None)
        return scrub_event(event)

    return before_send


def init_sentry(process: Process, *, transport: Any = None) -> bool:
    """Start Sentry for this process; return whether it was enabled."""
    settings = SentrySettings()
    if settings.sentry_dsn is None or not settings.sentry_dsn.get_secret_value():
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("SM_SENTRY_DSN is set but sentry-sdk is not installed; install the extra")
        return False
    before_send: Any = build_before_send(process)  # sentry types Event as a TypedDict
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        include_local_variables=False,  # frame locals hold the ASGI scope: headers, tokens
        max_request_body_size="never",
        before_send=before_send,
        before_send_transaction=before_send,
        transport=transport,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            CeleryIntegration(),
        ],
    )
    global _enabled
    _enabled = True
    logger.info("Sentry enabled for %s process", process)
    return True
