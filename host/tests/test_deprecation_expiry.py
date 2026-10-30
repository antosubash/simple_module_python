"""Compat shims must not outlive their ``remove_in`` release (#515).

Every shim registers with ``simple_module_core.deprecation``; this imports them
all and fails once the installed framework version reaches a registered
``remove_in``. Reaching it forces a decision: delete the shim (and this entry's
import), or consciously move its date.
"""

from __future__ import annotations

import importlib
import warnings
from importlib.metadata import version

import pytest
from simple_module_core.deprecation import (
    deprecate,
    expired_deprecations,
    registered_deprecations,
)

# Modules whose import registers a deprecation (shim modules and call-site shims).
_SHIM_MODULES = (
    "auth.deps",
    "host.routes_legacy",
    "permissions.deps",
    "settings.registration",
    "settings.module_registry",
    "settings.hydrate",
    "simple_module_hosting._registrations",
    "simple_module_core.public_routes",
    "simple_module_core.versioning",
)
_EXPECTED = {
    "auth.deps.require_permission",
    "host.routes_legacy (pre-/admin view URL redirects)",
    "permissions.deps.invalidate_grants_on_commit",
    "settings.registration",
    "settings.module_registry",
    "settings.hydrate",
    "AuthProvider.get_public_paths",
    "register_event_handlers(self, bus) without the app parameter",
    "simple_module_inertia.props.lazy",
    "ModuleBase.register_event_handlers app=None default",
    "ModuleMeta.requires_framework=None compatibility bypass",
}


def _register_all() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for name in _SHIM_MODULES:
            importlib.import_module(name)
    # Overrides own event-hook calls, so omission cannot warn reliably at the base.
    from simple_module_core.module import EVENT_HANDLERS_OPTIONAL_APP_REMOVE_IN

    deprecate(
        "ModuleBase.register_event_handlers app=None default",
        remove_in=EVENT_HANDLERS_OPTIONAL_APP_REMOVE_IN,
        use="register_event_handlers(self, bus, app) with an explicit app argument",
    )
    # simple_module_inertia is standalone (no core dependency), so it exposes a
    # constant instead of registering itself.
    from simple_module_inertia import props

    deprecate("simple_module_inertia.props.lazy", remove_in=props.LAZY_REMOVE_IN, use="optional()")


def test_every_known_shim_is_registered() -> None:
    _register_all()
    assert {d.name for d in registered_deprecations()} >= _EXPECTED


def test_no_shim_outlives_its_remove_in_release() -> None:
    _register_all()
    expired = expired_deprecations(version("simple_module_core"))
    if expired:
        listing = "\n".join(f"  - {d.name} (remove_in {d.remove_in})" for d in expired)
        pytest.fail(
            "These deprecations reached their removal release; delete them (or move "
            f"remove_in on purpose):\n{listing}"
        )
