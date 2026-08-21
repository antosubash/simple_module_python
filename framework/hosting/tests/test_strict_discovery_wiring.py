"""``create_app(settings)`` must propagate strict-discovery in non-dev environments.

``app_builder.create_app`` calls ``discover_modules(strict=not settings.is_development)``.
The existing tests cover ``discover_modules`` directly with strict=True, but
nothing pins the wiring — a regression that hard-coded ``strict=False`` would
silently restore the old "drop a broken module and keep booting" behaviour in
production, which is exactly what CLAUDE.md says must not happen.

Reuses the ``_FakeEntryPoint`` and ``_patch_entry_points`` helpers from
``framework/core/tests/test_discovery.py`` (the canonical location for the
entry-point stubbing pattern) rather than redeclaring the same shim here.
"""

from __future__ import annotations

import contextlib
import importlib.util
from pathlib import Path

import pytest
from simple_module_core.exceptions import InvalidModuleError
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings


def _load_discovery_helpers():
    """Side-load ``framework/core/tests/test_discovery.py`` without mutating ``sys.path``.

    The core-tests directory isn't a package (no ``__init__.py``), and adding
    it to ``sys.path`` would expose every ``test_*`` module in there as a
    top-level import for the rest of the session — risking name collisions.
    ``spec_from_file_location`` loads just the one file we need into a
    private namespace.
    """
    discovery_path = Path(__file__).resolve().parents[2] / "core" / "tests" / "test_discovery.py"
    spec = importlib.util.spec_from_file_location("_core_test_discovery_helpers", discovery_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._FakeEntryPoint, mod._boom_loader, mod._patch_entry_points


_FakeEntryPoint, _boom_loader, _patch_entry_points = _load_discovery_helpers()


class _NotAModule:
    """A class returned by an entry point that isn't a ModuleBase subclass."""


def _prod_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="production",
        secret_key="x" * 32,
        multi_tenant=False,
    )


def test_create_app_in_production_fails_on_broken_entrypoint(monkeypatch):
    """A failed entry-point load in production must abort ``create_app``."""
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("boom", _boom_loader)])
    with pytest.raises(InvalidModuleError, match="Failed to load"):
        create_app(_prod_settings())


def test_create_app_in_production_fails_on_non_modulebase(monkeypatch):
    """Same contract for non-ModuleBase classes registered as entry points."""
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("notmod", _NotAModule)])
    with pytest.raises(InvalidModuleError, match="not a ModuleBase"):
        create_app(_prod_settings())


def test_discover_modules_called_with_strict_mirroring_environment(monkeypatch):
    """The wiring assertion: ``app_builder`` passes ``strict=not is_development``.

    We don't actually run ``create_app`` in dev — that triggers Inertia setup
    and ``emit_frontend_types_for_modules``, which mutates the generated i18n type files
    on disk because the entry-point stub yields zero modules. Asserting the
    keyword argument is sufficient to pin the wiring contract.
    """
    captured: dict[str, object] = {}

    def _spy(*args, **kwargs):
        captured["strict"] = kwargs.get("strict")
        return []

    monkeypatch.setattr("simple_module_hosting.app_builder.discover_modules", _spy)
    # Block dev-mode side effects (write_module_pages_manifest +
    # emit_frontend_types_for_modules) — with zero modules they'd rewrite the
    # generated i18n files to empty.
    monkeypatch.setattr(
        "simple_module_hosting.app_builder.emit_frontend_types_for_modules",
        lambda *a, **kw: None,
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
