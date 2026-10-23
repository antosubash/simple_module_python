"""Shared public access, including the pre-0.1.0 provider shim."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from simple_module_core.app_state import get_auth_provider, get_public_routes
from simple_module_core.public_routes import legacy_provider_public_paths

logger = logging.getLogger(__name__)
_provider_failure_warned = False


def is_public(app: FastAPI, method: str, path: str) -> bool:
    """Whether the registry or legacy provider opens this concrete path."""
    registry = get_public_routes(app)
    if registry is not None and registry.matches(method, path):
        return True
    provider = get_auth_provider(app)
    if provider is None:
        return False
    try:
        prefixes, exact = legacy_provider_public_paths(provider)
    except Exception:
        # Runs per request (and per route x placeholder in SM031): warn once per
        # process, per the error-handling policy, instead of a traceback each time.
        global _provider_failure_warned
        if not _provider_failure_warned:
            _provider_failure_warned = True
            logger.warning("Auth provider failed to report public paths", exc_info=True)
        return False
    return any(path.startswith(prefix) for prefix in prefixes) or path in exact
