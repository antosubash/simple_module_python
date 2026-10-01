"""Diagnostics that need the built app, so cannot run from ``make doctor``.

The module diagnostics in Phase 2 see only module classes and the source tree.
A check about what modules *registered* has to wait until after Phase 5, and
unlike the source-tree checks it is meaningful in production too.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from simple_module_core.diagnostics import Diagnostic, check_tenant_resolver, print_diagnostics

if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.services import DiagnosticsState

logger = logging.getLogger(__name__)


def _tenant_checks(app: FastAPI, settings: Any) -> list[Diagnostic]:
    return check_tenant_resolver(
        multi_tenant=bool(getattr(settings, "multi_tenant", False)),
        resolver=getattr(app.state, "tenant_resolver", None),
    )


def report_tenant_resolution(
    app: FastAPI, settings: Any, diagnostics_state: DiagnosticsState
) -> list[Diagnostic]:
    """SM025: report, and fold into the Doctor screen's results when it has a runner."""
    found = _tenant_checks(app, settings)
    if found:
        if settings.is_development:
            print_diagnostics(found)
        else:
            for diag in found:
                logger.warning("%s", diag)
    runner = diagnostics_state.runner
    if runner is not None:
        diagnostics_state.runner = lambda: [*runner(), *_tenant_checks(app, settings)]
        diagnostics_state.results = [*diagnostics_state.results, *found]
    return found


__all__ = ["report_tenant_resolution"]
