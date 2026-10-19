"""Host-settings registration and its SM012 check (split from ``_phase_helpers``)."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel

from simple_module_hosting._host_services import _HostServices
from simple_module_hosting.host_settings import HostSettings


def register_host_settings(app: FastAPI) -> None:
    """Register host-level settings under ``package="host"`` (DB-backed).

    The Settings module must already have run ``register_settings`` — topo
    order puts it early, since its ``meta.depends_on`` is empty. When the
    Settings module isn't enabled there's no registry to register against, so
    this skips quietly.

    ``settings.registration`` is resolved via importlib rather than a plain
    ``from settings.registration import ...``: the SM009 coupling check is
    AST-based and forbids any static import of a plugin package name from
    within ``framework/*``. Dynamic resolution keeps the framework AST
    plugin-free while still hitting the real helper at runtime.
    """
    if not hasattr(app.state, "settings"):
        return

    import importlib

    register_module_settings = importlib.import_module(
        "settings.registration"
    ).register_module_settings

    register_module_settings(app, "host", HostSettings, lambda s: _HostServices(settings=s))


def check_settings_registration(app: FastAPI, modules: list) -> list[Diagnostic]:
    """SM012: warn if a module overrides register_settings but added nothing to app.state.

    Must run after Phase 4 (register_settings) and therefore can't join the
    Phase 2 diagnostics pass; returning a list lets the caller route it through
    the same ``print_diagnostics`` sink.
    """
    diagnostics: list[Diagnostic] = []
    for mod in modules:
        cls = type(mod)
        if "register_settings" not in cls.__dict__:
            continue
        # Match the convention actually used by modules: `app.state.<package>`
        # (snake_case package name, e.g. `background_tasks`), which aligns
        # with Settings-module autodiscovery in `settings._module_settings`.
        package = cls.__module__.split(".", 1)[0]
        candidates = (package, mod.meta.name.lower())
        if any(hasattr(app.state, c) for c in candidates):
            continue
        mod_prefix = package
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM012",
                message="register_settings() was overridden but added nothing to app.state",
                module_name=mod.meta.name,
                suggestion=(
                    f"Store your module state on app.state "
                    f"(e.g., app.state.{mod_prefix} = {mod.meta.name}Services(...))"
                ),
            )
        )
    return diagnostics
