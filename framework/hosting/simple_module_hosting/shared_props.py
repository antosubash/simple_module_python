"""Module-registered Inertia shared-prop providers.

A generic extension point so plugin modules can contribute layout-wide Inertia
shared props (e.g. branding) on every page, without the framework importing the
plugin. This mirrors the ``principal_serializer`` precedent: the framework reads
a registered callable off ``app.state`` rather than reaching into module code,
keeping the ``SM009`` framework→plugin import ban intact.

A provider is ``Callable[[Request], dict]`` or an ``async`` one. It must be cheap
and total — it runs for every request. :class:`InertiaLayoutDataMiddleware` merges each provider's
returned dict into the ``shared`` payload after the built-in ``auth``/``menus``/
``i18n`` blocks; a provider that raises is skipped and logged, never failing the
request.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from simple_module_core.app_state import (
    INERTIA_SHARED_PROVIDERS_STATE_ATTR,
    get_inertia_shared_providers,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

SharedPropsProvider = Callable[["Request"], dict | Awaitable[dict]]
"""A function mapping a request to a dict merged into Inertia shared props."""


def register_inertia_shared_provider(app: FastAPI, provider: SharedPropsProvider) -> None:
    """Register a shared-props provider on the app.

    Idempotently initialises ``app.state.inertia_shared_providers`` (a list) and
    appends ``provider``. Safe to call from a module lifecycle hook before the
    framework has set up the list.
    """
    providers = get_inertia_shared_providers(app)
    if providers is None:
        providers = []
        setattr(app.state, INERTIA_SHARED_PROVIDERS_STATE_ATTR, providers)
    providers.append(provider)
