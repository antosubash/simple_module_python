"""Shared public access, including the pre-0.1.0 provider shim."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from simple_module_core.public_routes import legacy_provider_public_paths

logger = logging.getLogger(__name__)


def is_public(app: FastAPI, method: str, path: str) -> bool:
    """Whether the registry or legacy provider opens this concrete path."""
    registry = getattr(app.state, "public_routes", None)
    if registry is not None and registry.matches(method, path):
        return True
    provider = getattr(getattr(app.state, "auth", None), "auth_provider", None)
    if provider is None:
        return False
    try:
        prefixes, exact = legacy_provider_public_paths(provider)
    except Exception:
        logger.exception("Auth provider failed to report public paths")
        return False
    return any(path.startswith(prefix) for prefix in prefixes) or path in exact
