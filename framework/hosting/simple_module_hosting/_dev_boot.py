"""Development-only boot work: the diagnostics run and the frontend artifacts.

Extracted from ``app_builder`` so that file reads as the phase sequence and
nothing else. Everything here is gated on ``settings.is_development`` at the one
call site, and everything here reads or writes the *source tree* — a deployed
wheel has no ``host/client_app`` to write a manifest into and no module sources
for the AST checks to walk, which is why none of it belongs on a production boot
path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics import DiagnosticLevel, print_diagnostics, run_diagnostics

from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules

if TYPE_CHECKING:
    from simple_module_core import ModuleBase
    from simple_module_core.services import DiagnosticsState

    from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["run_dev_boot"]


def run_dev_boot(
    settings: Settings,
    modules: list[ModuleBase],
    installed_modules: list[ModuleBase],
    *,
    i18n_extra,
    diagnostics_state: DiagnosticsState,
    project_root: Path,
) -> None:
    """Run the module diagnostics and emit the frontend's generated files.

    ``diagnostics_state.runner`` is left behind on purpose, not just used: the
    in-app Doctor screen re-invokes this exact call through ``rerun()``, and
    re-deriving the arguments from a request would mean re-discovering modules.

    An ERROR-level diagnostic ends the process. A developer whose module has a
    duplicate name or a framework→plugin import gets one clear message here
    instead of an inexplicable failure several phases later — and the same
    checks run at production boot, where the app would refuse to start anyway.
    """
    diagnostics_state.runner = lambda: run_diagnostics(
        modules,
        i18n_supported_locales=settings.i18n_supported_locales,
        i18n_default_locale=settings.i18n_default_locale,
        i18n_extra_sources=i18n_extra,
    )
    diagnostics = diagnostics_state.rerun()
    errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
    if diagnostics:
        print_diagnostics(diagnostics)
    if errors:
        raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")

    _write_pages_manifest(modules, project_root)
    emit_frontend_types_for_modules(settings, installed_modules, project_root)


def _write_pages_manifest(modules: list[ModuleBase], project_root: Path) -> None:
    """Tell Vite where pages shipped inside pip-installed wheels live.

    Swallows its own failure: a missing or unwritable ``client_app`` must not
    stop the API from booting, and the symptom — pages the frontend cannot find
    — is loud enough on its own. See ``scaffolding.py``.
    """
    try:
        from simple_module_hosting.manifest import write_module_pages_manifest

        client_app = project_root / "host" / "client_app"
        if client_app.is_dir():
            write_module_pages_manifest(modules, client_app)
    except Exception:
        logger.exception("Failed to write module pages manifest — frontend may miss pages")
