"""Shared method-aware public access through the module registry."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.modules.app_state import get_public_routes


def is_public(app: FastAPI, method: str, path: str) -> bool:
    """Whether the public-route registry opens this concrete path."""
    registry = get_public_routes(app)
    return registry is not None and registry.matches(method, path)
