"""Feature flag registry — modules declare toggleable features.

Overrides live at two scopes:

* **system** — applies to every request unless a tenant override exists
* **tenant** — applies only when ``is_enabled`` is called with a matching
  ``tenant_id``; a per-tenant value beats the system override

Resolution order: tenant override > system override > definition default.

Consumers check a flag inside a FastAPI endpoint via ``is_flag_enabled``,
``flag_enabled``, ``require_flag``, or the ``@feature_flag`` decorator —
all tenant-aware using ``request.state.tenant_id`` set by
``TenantMiddleware``. Every helper accepts either a
``FeatureFlagDefinition`` (preferred: pass the constant you registered) or
the raw flag name.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


def _flag_name(flag: FeatureFlagDefinition | str) -> str:
    return flag.name if isinstance(flag, FeatureFlagDefinition) else flag


def is_flag_enabled(request: Request, flag: FeatureFlagDefinition | str) -> bool:
    """Return whether ``flag`` is enabled for this request's tenant context.

    Reads the registry from ``request.app.state.sm.feature_flags`` and the
    tenant from ``request.state.tenant_id`` (set by ``TenantMiddleware``).
    Without a tenant on the request, falls back to the system value or the
    definition default.
    """
    registry: FeatureFlagRegistry = request.app.state.sm.feature_flags
    tenant_id: str | None = getattr(request.state, "tenant_id", None)
    return registry.is_enabled(_flag_name(flag), tenant_id=tenant_id)


def flag_enabled(flag: FeatureFlagDefinition | str) -> Callable[[Request], bool]:
    """FastAPI dep factory — yields ``True`` when the flag is on.

    Usage::

        async def handler(
            on: Annotated[bool, Depends(flag_enabled(FLAG_NEW_UI))],
        ) -> ...:
            if on: ...
    """

    def _dep(request: Request) -> bool:
        return is_flag_enabled(request, flag)

    return _dep


def require_flag(flag: FeatureFlagDefinition | str) -> Callable[[Request], None]:
    """FastAPI dep factory — raises 404 when the flag is off.

    Gate an entire endpoint behind a flag::

        @router.post(
            "/bulk",
            dependencies=[Depends(require_flag(FLAG_BULK_IMPORT))],
        )
        async def bulk_import(...): ...
    """

    def _dep(request: Request) -> None:
        if not is_flag_enabled(request, flag):
            raise HTTPException(status_code=404, detail="Feature not available")

    return _dep


def feature_flag(
    flag: FeatureFlagDefinition | str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator — gates an endpoint behind a flag, 404s when off.

    Attribute-style alternative to ``Depends(require_flag(...))``: apply
    directly to the handler. The decorated function must accept a
    ``request: Request`` parameter (FastAPI injects it automatically).

    Usage::

        @router.post("/bulk")
        @feature_flag(FLAG_BULK_IMPORT)
        async def bulk_import(request: Request, payload: Payload): ...
    """
    name = _flag_name(flag)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn, eval_str=True)
        request_param = next(
            (p.name for p in sig.parameters.values() if p.annotation is Request),
            None,
        )
        if request_param is None:
            raise TypeError(
                f"@feature_flag({name!r}): {fn.__qualname__} must declare a "
                f"'request: Request' parameter for the decorator to read tenant state"
            )

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                request = sig.bind(*args, **kwargs).arguments[request_param]
                if not is_flag_enabled(request, name):
                    raise HTTPException(status_code=404, detail="Feature not available")
                return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            request = sig.bind(*args, **kwargs).arguments[request_param]
            if not is_flag_enabled(request, name):
                raise HTTPException(status_code=404, detail="Feature not available")
            return fn(*args, **kwargs)

        return sync_wrapper

    return decorator
