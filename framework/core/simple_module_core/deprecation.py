"""Deprecations that carry an enforced removal version (#515).

Every compat shim registers here with the release in which it must be deleted
(``remove_in``). ``host/tests/test_deprecation_expiry.py`` imports every shim and
fails once the installed framework version reaches any registered ``remove_in``,
so a shim cannot silently outlive its date: the release that reaches it forces a
decision (delete the shim, or consciously move the date).

Three entry points, one registry:

- :func:`deprecated` decorates a function or class; it warns on call/instantiation.
- :func:`deprecated_module` is called at module scope in a shim module; it warns at
  import and attributes the warning to the importer.
- :func:`deprecate` registers a call-site deprecation (a code path kept for old
  callers) and returns a handle whose ``warn()`` the path calls when it is taken.
"""

from __future__ import annotations

import functools
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from packaging.version import Version

_T = TypeVar("_T")
_IMPORTLIB_FRAMES = "<frozen importlib"


@dataclass(frozen=True)
class Deprecation:
    """One registered deprecation."""

    name: str
    remove_in: str
    use: str | None = None

    @property
    def message(self) -> str:
        text = f"{self.name} is deprecated and will be removed in {self.remove_in}"
        return f"{text}; use {self.use} instead" if self.use else text

    def warn(self, stacklevel: int = 2) -> None:
        """Emit the ``DeprecationWarning``; ``stacklevel=2`` blames our caller."""
        warnings.warn(self.message, DeprecationWarning, stacklevel=stacklevel + 1)


_REGISTRY: dict[str, Deprecation] = {}


def deprecate(name: str, *, remove_in: str, use: str | None = None) -> Deprecation:
    """Register (idempotently) and return the deprecation named ``name``."""
    Version(remove_in)  # fail at import, not at the release that needed it
    entry = Deprecation(name=name, remove_in=remove_in, use=use)
    _REGISTRY[name] = entry
    return entry


def deprecated(
    *, remove_in: str, use: str | None = None, name: str | None = None
) -> Callable[[_T], _T]:
    """Mark a function or class deprecated; calling/instantiating it warns."""

    def decorate(obj: _T) -> _T:
        label = name or f"{getattr(obj, '__module__', '?')}.{getattr(obj, '__qualname__', obj)}"
        entry = deprecate(label, remove_in=remove_in, use=use)
        if isinstance(obj, type):
            original_init = obj.__init__

            @functools.wraps(original_init)
            def init(self: Any, *args: Any, **kwargs: Any) -> None:
                entry.warn(stacklevel=2)
                original_init(self, *args, **kwargs)

            obj.__init__ = init  # ty: ignore[invalid-assignment]
            return obj

        @functools.wraps(cast("Callable[..., Any]", obj))
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            entry.warn(stacklevel=2)
            return cast("Callable[..., Any]", obj)(*args, **kwargs)

        return cast("_T", wrapper)

    return decorate


def deprecated_module(name: str, *, remove_in: str, use: str) -> None:
    """Call at module scope in a shim module: register and warn at import time."""
    entry = deprecate(name, remove_in=remove_in, use=use)
    # Skip this file, the shim itself and importlib so the warning names the importer.
    shim_file = sys._getframe(1).f_code.co_filename
    warnings.warn(
        entry.message,
        DeprecationWarning,
        skip_file_prefixes=(__file__, shim_file, _IMPORTLIB_FRAMES),
    )


def registered_deprecations() -> list[Deprecation]:
    """Every deprecation registered so far, by name."""
    return sorted(_REGISTRY.values(), key=lambda d: d.name)


def expired_deprecations(version: str) -> list[Deprecation]:
    """Deprecations due at ``version`` (a pre-release of the removal version counts)."""
    current = Version(Version(version).base_version)
    return [d for d in registered_deprecations() if current >= Version(d.remove_in)]
