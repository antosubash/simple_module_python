"""The first-run setup wizard, shipped with the framework.

``SetupMiddleware`` redirects every request to ``/setup`` while a required
:class:`~simple_module_core.setup_steps.SetupStep` is incomplete. The wizard
those redirects land on used to live in this repository's own host, so any
other host taking the package got ``/`` → ``/setup`` → 404 (GH #351).
``create_app`` now mounts it for every host.

The wizard is generic: it lists the registered steps and renders a form for
each pending step that carries a :class:`~simple_module_core.setup_steps.SetupAction`.
What a step's form *does* belongs to the module that owns the step — the
framework never imports a plugin module (SM009); the module hands the wizard a
handler instead.

The page ships from this package too: :func:`pages_dir` is registered in
``modules.generated.ts`` under :data:`PAGES_NAME`, exactly like a module's
``pages/``, so a host's Vite build picks it up from the wheel.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: The ``modules.generated.ts`` key the wizard's pages are registered under —
#: ``pages/Wizard.tsx`` resolves as the Inertia page ``Setup/Wizard``.
PAGES_NAME = "Setup"

_PACKAGE_DIR = Path(__file__).resolve().parent


def package_dir() -> Path:
    """The wizard's frontend root (``pages/`` and ``components/``)."""
    return _PACKAGE_DIR


def pages_dir() -> Path:
    return _PACKAGE_DIR / "pages"


def mount_setup_wizard(app, setup_registry) -> None:
    """Mount ``/setup`` and report steps the wizard cannot complete.

    Mounted unconditionally: every route refuses (404) once setup is complete,
    so on a configured install this is inert. An install with no registered
    step never reaches it, because the middleware never redirects there.
    """
    from simple_module_hosting.setup_wizard.routes import router

    app.include_router(router)
    report_unactionable_steps(setup_registry)


def report_unactionable_steps(setup_registry) -> None:
    """Log required steps that carry no wizard action.

    Such a step can only be completed out of band — a CLI command, an
    environment variable. Without this line an operator facing a wizard with
    no form has nothing to tell them why, which is the silent dead end
    GH #351 reported.
    """
    for step in setup_registry.required_steps:
        if step.action is None:
            logger.warning(
                "Setup step %r (module %r) is required but offers no wizard action; "
                "while it is incomplete the app redirects to /setup and the step "
                "must be completed out of band.",
                step.id,
                step.module or "host",
            )
