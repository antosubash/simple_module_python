"""Inertia.js v3 server adapter for FastAPI. See README.md and NOTICE."""

from __future__ import annotations

from simple_module_inertia.assets.head import Head, SiteInfo
from simple_module_inertia.assets.templating import InertiaExtension
from simple_module_inertia.protocol.config import InertiaConfig
from simple_module_inertia.protocol.errors import (
    InertiaVersionConflictException,
    inertia_request_validation_exception_handler,
    inertia_version_conflict_exception_handler,
)
from simple_module_inertia.protocol.middleware import InertiaMiddleware
from simple_module_inertia.protocol.request import INERTIA_HEADER, is_inertia_request
from simple_module_inertia.protocol.response import InertiaResponse
from simple_module_inertia.protocol.validation import errors_from_validation, scope_errors
from simple_module_inertia.rendering.deps import inertia_dependency_factory
from simple_module_inertia.rendering.inertia import Inertia
from simple_module_inertia.rendering.page import PropEncodingError
from simple_module_inertia.rendering.props import (
    always,
    deep_merge,
    defer,
    merge,
    once,
    optional,
    prepend,
    scroll,
)

__all__ = [
    "INERTIA_HEADER",
    "Head",
    "Inertia",
    "InertiaConfig",
    "InertiaExtension",
    "InertiaMiddleware",
    "InertiaResponse",
    "InertiaVersionConflictException",
    "PropEncodingError",
    "SiteInfo",
    "always",
    "deep_merge",
    "defer",
    "errors_from_validation",
    "inertia_dependency_factory",
    "inertia_request_validation_exception_handler",
    "inertia_version_conflict_exception_handler",
    "is_inertia_request",
    "merge",
    "once",
    "optional",
    "prepend",
    "scope_errors",
    "scroll",
]
