"""Feature flag registry — modules declare toggleable features.

Overrides live at two scopes:

* **system** — applies to every request unless a tenant override exists
* **tenant** — applies only when ``is_enabled`` is called with a matching
  ``tenant_id``; a per-tenant value beats the system override

Resolution order: tenant override > system override > definition default.

Consumers check a flag inside a FastAPI endpoint via ``is_flag_enabled``,
``flag_enabled``, or ``require_flag`` — all tenant-aware using
``request.state.tenant_id`` set by ``TenantMiddleware``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class FeatureFlagDefinition:
    """A feature that can be toggled on/off at runtime."""

    name: str
    description: str = ""
    default_enabled: bool = False


class FeatureFlagRegistry:
    """In-memory registry of flag definitions and their resolved overrides."""

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlagDefinition] = {}
        self._system_overrides: dict[str, bool] = {}
        self._tenant_overrides: dict[tuple[str, str], bool] = {}

    def add(self, flag: FeatureFlagDefinition) -> None:
        self._flags[flag.name] = flag

    def is_enabled(self, name: str, tenant_id: str | None = None) -> bool:
        if tenant_id is not None:
            tenant_value = self._tenant_overrides.get((name, tenant_id))
            if tenant_value is not None:
                return tenant_value
        if name in self._system_overrides:
            return self._system_overrides[name]
        flag = self._flags.get(name)
        return flag.default_enabled if flag else False

    def set_override(self, name: str, enabled: bool, tenant_id: str | None = None) -> None:
        if tenant_id is None:
            self._system_overrides[name] = enabled
        else:
            self._tenant_overrides[(name, tenant_id)] = enabled

    def clear_override(self, name: str, tenant_id: str | None = None) -> None:
        if tenant_id is None:
            self._system_overrides.pop(name, None)
        else:
            self._tenant_overrides.pop((name, tenant_id), None)

    def tenant_override(self, name: str, tenant_id: str) -> bool | None:
        """Return the per-tenant override for ``(name, tenant_id)`` if set, else None."""
        return self._tenant_overrides.get((name, tenant_id))

    def system_override(self, name: str) -> bool | None:
        """Return the system-level override for ``name`` if set, else None."""
        return self._system_overrides.get(name)

    @property
    def all_flags(self) -> list[FeatureFlagDefinition]:
        return list(self._flags.values())


def is_flag_enabled(request: Request, name: str) -> bool:
    """Return whether ``name`` is enabled for this request's tenant context.

    Reads the registry from ``request.app.state.sm.feature_flags`` and the
    tenant from ``request.state.tenant_id`` (set by ``TenantMiddleware``).
    Without a tenant on the request, falls back to the system value or the
    definition default.
    """
    registry: FeatureFlagRegistry = request.app.state.sm.feature_flags
    tenant_id: str | None = getattr(request.state, "tenant_id", None)
    return registry.is_enabled(name, tenant_id=tenant_id)


def flag_enabled(name: str) -> Callable[[Request], bool]:
    """FastAPI dep factory — yields ``True`` when the flag is on.

    Usage::

        async def handler(
            on: Annotated[bool, Depends(flag_enabled("new_ui"))],
        ) -> ...:
            if on: ...
    """

    def _dep(request: Request) -> bool:
        return is_flag_enabled(request, name)

    return _dep


def require_flag(name: str) -> Callable[[Request], None]:
    """FastAPI dep factory — raises 404 when the flag is off.

    Gate an entire endpoint behind a flag::

        @router.post(
            "/bulk",
            dependencies=[Depends(require_flag("products.bulk_import"))],
        )
        async def bulk_import(...): ...
    """

    def _dep(request: Request) -> None:
        if not is_flag_enabled(request, name):
            raise HTTPException(status_code=404, detail="Feature not available")

    return _dep
