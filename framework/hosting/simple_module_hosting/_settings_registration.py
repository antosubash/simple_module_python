"""Host-settings registration and its SM012 check (split from ``_phase_helpers``)."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.module_settings import register_module_settings

from simple_module_hosting._host_services import _HostServices
from simple_module_hosting._preapp_config import HOST_PACKAGE
from simple_module_hosting.host_settings import HostSettings


def register_host_settings(app: FastAPI) -> None:
    """Register host-level settings under ``package="host"`` (DB-backed).

    The registry belongs to the framework (#500), so this no longer depends on
    the ``settings`` plugin having registered first, or being enabled at all.
    """
    register_module_settings(app, HOST_PACKAGE, HostSettings, lambda s: _HostServices(settings=s))


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
