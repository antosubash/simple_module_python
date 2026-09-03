"""Real data for the Doctor screen — the in-app mirror of ``make doctor``.

Everything here reads live state: the diagnostics run the boot kept on
``app.state.sm.diagnostics``, the migration state the lifespan already checked,
the Alembic script directory, and the process's own settings. Nothing is
sampled or mocked — a panel with no real source renders an empty state saying
so rather than a plausible-looking number.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_hosting.migrations import list_migrations

logger = logging.getLogger(__name__)

#: Command copied by a check's "Fix" action. Running Alembic — or anything
#: else — from a web request is not something this app does, so the screen
#: hands the operator the line to paste into their own shell.
_DOCTOR_COMMAND = "make doctor"
MIGRATION_CHECK_ID = "migrations"


@dataclass(frozen=True)
class DoctorCheck:
    """One named check on the screen, backed by a set of diagnostic codes.

    The diagnostics engine reports *findings*; the screen reports *checks*, so
    that "7 of 8 passing" means something even on a clean install where there
    are no findings at all. Each check owns the codes it answers for.
    """

    id: str
    codes: frozenset[str]
    command: str = _DOCTOR_COMMAND


#: The catalogue. Labels live in the locale catalogue keyed by ``id`` — this is
#: the framework's own diagnostic surface (see CLAUDE.md § Diagnostic codes),
#: grouped into the questions an operator actually asks.
CHECKS: tuple[DoctorCheck, ...] = (
    DoctorCheck("pages", frozenset({"SM003", "SM004"}), "make gen-pages"),
    DoctorCheck("metadata", frozenset({"SM001", "SM008", "SM012", "SM017", "SM019"})),
    DoctorCheck("coupling", frozenset({"SM009"})),
    DoctorCheck(MIGRATION_CHECK_ID, frozenset({"SM010", "SM011"}), "make migrations"),
    DoctorCheck("locales", frozenset({"SM013", "SM014", "SM015", "SM016"}), "make gen-i18n"),
    DoctorCheck("inertia", frozenset({"SM018"})),
    DoctorCheck("auth_provider", frozenset({"SM020", "SM021"})),
    DoctorCheck("styling", frozenset({"SM022", "SM023"})),
)

_STATUS_PASS = "pass"
_STATUS_WARN = "warn"
_STATUS_FAIL = "fail"
#: Development-only checks, seen from a deployment that never ran them.
_STATUS_UNKNOWN = "unknown"

#: Commands the migrations panel's link actions copy, per the deck's
#: "Generate" / "Apply pending".
MIGRATION_COMMANDS = {"generate": "make migrations", "apply": "make migrate"}

#: Shown when nothing reports a worker — honest about the absence rather than
#: inventing a hostname.
NO_VALUE = "—"

_SCHEME_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _relative(file: str | None) -> str | None:
    """Trim the working directory off absolute finding paths for display."""
    if not file:
        return file
    try:
        return str(Path(file).relative_to(Path.cwd()))
    except ValueError:
        return file


def _finding(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "level": diagnostic.level.value,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "module": diagnostic.module_name,
        "file": _relative(diagnostic.file),
        "suggestion": diagnostic.suggestion,
    }


def _status(findings: list[Diagnostic]) -> str:
    if any(d.level == DiagnosticLevel.ERROR for d in findings):
        return _STATUS_FAIL
    if any(d.level == DiagnosticLevel.WARNING for d in findings):
        return _STATUS_WARN
    return _STATUS_PASS


def collect_checks(app: FastAPI) -> list[dict[str, Any]]:
    """The eight named checks, each with the findings it owns.

    Reads the boot run rather than re-running: the AST sweep behind SM003/SM009
    walks every source file in the workspace, which is far too expensive to do
    on a page load. ``POST /admin/doctor/rerun`` is how a fresh run is asked
    for.

    Info-level findings (SM007 "module overrides no hooks") are remarks about
    a module's shape, not defects, so they are neither listed nor counted —
    a check that "fails" on one would make a clean install look broken.
    """
    state = app.state.sm.diagnostics
    by_code: dict[str, list[Diagnostic]] = {}
    if state.supported:
        for diagnostic in state.results:
            if diagnostic.level == DiagnosticLevel.INFO:
                continue
            by_code.setdefault(diagnostic.code, []).append(diagnostic)

    rows: list[dict[str, Any]] = []
    for check in CHECKS:
        findings = [d for code in sorted(check.codes) for d in by_code.get(code, [])]
        rows.append(
            {
                "id": check.id,
                "status": _status(findings) if state.supported else _STATUS_UNKNOWN,
                "command": check.command,
                "findings": [_finding(d) for d in findings],
            }
        )
    return rows


def _port_label(url: str) -> str:
    """``http://localhost:5050`` → ``:5050``, falling back to the scheme's port."""
    parts = urlsplit(url)
    port = parts.port or _SCHEME_PORTS.get(parts.scheme, 80)
    return f":{port}"


def _worker_name(app: FastAPI) -> str:
    """The first online worker of the last fleet poll, or ``—``.

    Duck-typed off ``app.state.background_tasks.last_worker_snapshot`` on
    purpose: that module is optional, and importing it here would couple the
    dashboard to a package a given install may not have. Nothing polls on this
    screen's behalf, so the row reports the *last* poll or nothing at all —
    naming a worker we never heard from would be the fixture problem again.
    """
    snapshot = getattr(getattr(app.state, "background_tasks", None), "last_worker_snapshot", None)
    for worker in getattr(snapshot, "workers", None) or ():
        if getattr(worker, "online", False) and getattr(worker, "hostname", ""):
            return str(worker.hostname)
    return NO_VALUE


def dev_server(request: Request) -> dict[str, Any]:
    """Vite / api / worker, from settings, the request and the task module.

    ``running`` says whether this process is serving assets from the Vite dev
    server at all — the same condition ``_inertia_setup`` uses to choose
    between the dev server and the built manifest.
    """
    from simple_module_core.environments import NON_PROD_ENVIRONMENTS

    settings = request.app.state.sm.settings
    return {
        "running": settings.environment in NON_PROD_ENVIRONMENTS,
        "rows": [
            {"name": "vite", "value": _port_label(settings.vite_dev_url)},
            {"name": "api", "value": _port_label(str(request.url))},
            {"name": "worker", "value": _worker_name(request.app)},
        ],
    }


def migration_rows(app: FastAPI) -> list[dict[str, Any]]:
    """Recent Alembic revisions with the applied flag this database earns."""
    state = getattr(app.state, "migration", None) or {}
    return list_migrations(current_revision=state.get("current_revision"))


def _module_pages_dir(module: Any) -> Path | None:
    package = type(module).__module__.split(".", 1)[0]
    try:
        spec = importlib.util.find_spec(package)
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        return None
    locations = list(spec.submodule_search_locations or ()) if spec else []
    return Path(locations[0]) / "pages" if locations else None


def count_pages(app: FastAPI) -> int:
    """How many Inertia pages the installed modules ship.

    The same set SM003 diffs against ``inertia.render`` calls, so the number in
    the transcript panel is the number the orphan-page check reasoned about.
    """
    from simple_module_core.diagnostics._pages import collect_tsx_pages

    total = 0
    for module in app.state.sm.modules:
        pages_dir = _module_pages_dir(module)
        if pages_dir is not None and pages_dir.is_dir():
            total += len(collect_tsx_pages(pages_dir))
    return total


def doctor_props(request: Request, *, module_count: int) -> dict[str, Any]:
    """Everything the Doctor screen renders, all of it live."""
    app = request.app
    checks = collect_checks(app)
    migration = getattr(app.state, "migration", None) or {}
    return {
        "checks": checks,
        "checks_available": app.state.sm.diagnostics.supported,
        "migrations": migration_rows(app),
        "migration_commands": MIGRATION_COMMANDS,
        "dev_server": dev_server(request),
        "pages_routed": count_pages(app),
        "stats": {
            "checks_passing": sum(1 for c in checks if c["status"] == _STATUS_PASS),
            "checks_total": len(checks),
            "modules_loaded": module_count,
            "pending_migrations": migration.get("pending_count", 0),
            "python_version": (
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            ),
        },
    }
