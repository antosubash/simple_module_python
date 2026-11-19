"""Auth capability declaration and the dated class-marker fallback (#960)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from weakref import WeakSet

from simple_module_core.deprecation import deprecate

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

_LEGACY_MARKER = deprecate(
    "ModuleBase._is_auth_provider",
    remove_in="0.1.0",
    use="ModuleMeta(provides_auth=True)",
)
_WARNED: WeakSet[type] = WeakSet()


def provides_auth(module: ModuleBase) -> bool:
    """Use the public declaration, accepting legacy providers until removal."""
    legacy = bool(getattr(module, "_is_auth_provider", False))
    if legacy and type(module) not in _WARNED:
        _LEGACY_MARKER.warn(stacklevel=2)
        _WARNED.add(type(module))
    return module.meta.provides_auth or legacy


def resembles_auth_provider(module: ModuleBase) -> bool:
    """Recognize the protocol shape on the module without importing a plugin.

    Separate provider objects created by register_settings are not visible here.
    """
    return isinstance(getattr(module, "name", None), str) and all(
        callable(getattr(module, method, None))
        for method in ("resolve_user", "get_login_url", "get_logout_url", "is_bearer_request")
    )
