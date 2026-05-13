"""``create_app(settings)`` must propagate strict-discovery in non-dev environments.

``app_builder.create_app`` calls ``discover_modules(strict=not settings.is_development)``.
The existing tests cover ``discover_modules`` directly with strict=True, but
nothing pins the wiring — a regression that hard-coded ``strict=False`` would
silently restore the old "drop a broken module and keep booting" behaviour in
production, which is exactly what CLAUDE.md says must not happen.

This test stubs ``entry_points`` for the lifetime of the call so we don't have
to install a deliberately-broken plugin.
"""

from __future__ import annotations

import contextlib

import pytest
from simple_module_core.exceptions import InvalidModuleError
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings


class _BoomEntryPoint:
    """Entry point whose ``.load()`` raises — simulates a corrupt wheel."""

    name = "boom"

    @staticmethod
    def load():  # pragma: no cover - body intentionally fails
        raise ImportError("simulated broken plugin")


class _NotAModule:
    """A class returned by an entry point that isn't a ModuleBase subclass."""


class _NotAModuleEP:
    name = "notmod"

    @staticmethod
    def load():
        return _NotAModule


def _patch_eps(monkeypatch, eps):
    import simple_module_core.discovery as discovery_mod

    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: eps)


def _prod_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="production",
        secret_key="x" * 32,
        multi_tenant=False,
    )


def test_create_app_in_production_fails_on_broken_entrypoint(monkeypatch):
    """A failed entry-point load in production must abort ``create_app``."""
    _patch_eps(monkeypatch, [_BoomEntryPoint()])
    with pytest.raises(InvalidModuleError, match="Failed to load"):
        create_app(_prod_settings())


def test_create_app_in_production_fails_on_non_modulebase(monkeypatch):
    """Same contract for non-ModuleBase classes registered as entry points."""
    _patch_eps(monkeypatch, [_NotAModuleEP()])
    with pytest.raises(InvalidModuleError, match="not a ModuleBase"):
        create_app(_prod_settings())


def test_discover_modules_called_with_strict_mirroring_environment(monkeypatch):
    """The wiring assertion: ``app_builder`` passes ``strict=not is_development``.

    We don't actually run ``create_app`` in dev — that triggers Inertia setup
    and ``emit_frontend_types``, which mutates the generated i18n type files
    on disk because the entry-point stub yields zero modules. Asserting the
    keyword argument is sufficient to pin the wiring contract.
    """
    captured: dict[str, object] = {}

    def _spy(*args, **kwargs):
        captured["strict"] = kwargs.get("strict")
        return []

    monkeypatch.setattr("simple_module_hosting.app_builder.discover_modules", _spy)
    # Block dev-mode side effects (write_module_pages_manifest +
    # emit_frontend_types) — with zero modules they'd rewrite the
    # generated i18n files to empty.
    monkeypatch.setattr(
        "simple_module_hosting.app_builder.emit_frontend_types", lambda *a, **kw: None
    )
    import simple_module_hosting.manifest as manifest_mod

    monkeypatch.setattr(manifest_mod, "write_module_pages_manifest", lambda *a, **kw: None)

    # Dev environment — strict must be False.
    dev = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="development",
        secret_key="x" * 32,
        multi_tenant=False,
    )
    # Builder will fail later (no Inertia templates, no settings module),
    # but we already captured ``strict`` from the spy.
    with contextlib.suppress(Exception):
        create_app(dev)
    assert captured.get("strict") is False, "Dev mode must pass strict=False"

    # Production environment — strict must be True.
    captured.clear()
    prod = _prod_settings()
    with contextlib.suppress(Exception):
        create_app(prod)
    assert captured.get("strict") is True, "Production mode must pass strict=True"
