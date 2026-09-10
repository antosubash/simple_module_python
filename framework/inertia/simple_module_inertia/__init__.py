"""Inertia.js v3 server adapter for FastAPI. See README.md and NOTICE."""

from __future__ import annotations

from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.deps import inertia_dependency_factory
from simple_module_inertia.errors import (
    InertiaVersionConflictException,
    inertia_request_validation_exception_handler,
    inertia_version_conflict_exception_handler,
)
from simple_module_inertia.inertia import Inertia
from simple_module_inertia.page import PropEncodingError
from simple_module_inertia.props import (
    always,
    deep_merge,
    defer,
    lazy,
    merge,
    once,
    optional,
    prepend,
    scroll,
)
from simple_module_inertia.response import InertiaResponse
from simple_module_inertia.templating import InertiaExtension

__all__ = [
    "Inertia",
    "InertiaConfig",
    "InertiaExtension",
    "InertiaResponse",
    "InertiaVersionConflictException",
    "PropEncodingError",
    "always",
    "deep_merge",
    "defer",
    "inertia_dependency_factory",
    "inertia_request_validation_exception_handler",
    "inertia_version_conflict_exception_handler",
    "lazy",
    "merge",
    "once",
    "optional",
    "prepend",
    "scroll",
]
