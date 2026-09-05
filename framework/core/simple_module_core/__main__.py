"""Run module diagnostics from the command line.

Usage::

    python -m simple_module_core        # discover modules, run diagnostics
    make doctor                         # same thing, wrapped

Exits with status 1 if any ERROR-level diagnostics are reported.

i18n checks always run. ``SM_I18N_SUPPORTED_LOCALES`` (env or ``.env``)
declares the locale set this install promises, which also enables SM013 for a
namespace that never shipped one; with it unset, each namespace is checked
against the locale files it actually has, so key drift between two shipped
translations is still caught. Host-level ``host/locales/`` and shared
``packages/ui/locales/`` are picked up relative to the project root
(``SM_PROJECT_ROOT``, else the directory of the discovered ``.env``, else the
current working dir).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from simple_module_core.diagnostics import (
    Diagnostic,
    DiagnosticLevel,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.discovery import (
    discover_modules,
    resolve_auth_provider,
    select_auth_provider,
    topological_sort,
)
from simple_module_core.dotenv import find_env_file, parse_dotenv
from simple_module_core.exceptions import InvalidModuleError


def _load_i18n_settings_from_env() -> tuple[list[str] | None, str]:
    """Return ``(supported_locales, default_locale)``.

    ``supported_locales`` is ``None`` when ``SM_I18N_SUPPORTED_LOCALES`` is
    unset or unparseable — the diagnostic then falls back to the locale files
    each namespace ships rather than running no locale checks at all. The
    default locale always has a value, because a parity comparison needs to
    know which side is the source of truth.

    Reads env vars directly to avoid a dependency on ``simple_module_hosting``.
    Honors ``.env`` by merging it into ``os.environ`` if present (pydantic-
    settings isn't imported here).
    """
    for key, value in parse_dotenv().items():
        os.environ.setdefault(key, value)

    default = os.environ.get("SM_I18N_DEFAULT_LOCALE", "en")
    supported_raw = os.environ.get("SM_I18N_SUPPORTED_LOCALES")
    if not supported_raw:
        return None, default

    try:
        supported = json.loads(supported_raw)
    except json.JSONDecodeError:
        # Also accept comma-separated (e.g. "en,es,de").
        supported = [s.strip() for s in supported_raw.split(",") if s.strip()]

    if not isinstance(supported, list) or not supported:
        return None, default

    return supported, default


def _discover_extra_locale_sources() -> list[tuple[str, str, Path]]:
    """Return ``[(reporter, namespace, path), ...]`` for host + ui locale dirs."""
    # Anchor on the same project root the `.env` was loaded from
    # (`parse_dotenv` walks up from the cwd) — resolving against the bare cwd
    # here would look for `host/locales` in the wrong directory whenever
    # doctor runs from a subdirectory.
    root = find_env_file().parent
    out: list[tuple[str, str, Path]] = []
    host_locales = root / "host" / "locales"
    if host_locales.is_dir():
        out.append(("host", "host", host_locales))
    ui_locales = root / "packages" / "ui" / "locales"
    if ui_locales.is_dir():
        out.append(("packages/ui", "ui", ui_locales))
    return out


def main() -> int:
    # ``make doctor`` exists specifically to surface broken modules. The
    # default (lenient) discovery would silently skip a module whose entry
    # point fails to load, so doctor would report "all clear" while a
    # feature was missing from the boot. Use strict and translate the
    # raised error into a diagnostic so the rest of the run still happens.
    try:
        modules = discover_modules(strict=True)
    except InvalidModuleError as exc:
        print_diagnostics(
            [
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SM001",
                    message=str(exc),
                    module_name="<discovery>",
                    suggestion=(
                        "Fix the entry point above (broken import, missing 'meta', "
                        "or a class that isn't a ModuleBase subclass). Re-run "
                        "`make doctor` once resolved."
                    ),
                )
            ]
        )
        return 1

    if not modules:
        print("No modules discovered. Is the project installed (`uv sync --all-packages`)?")
        return 0

    # Mirror the host: only the configured auth provider is active, so doctor
    # reports on the same module set the app actually boots with.
    modules = select_auth_provider(modules, resolve_auth_provider())

    # Topological sort surfaces CircularDependencyError early.
    modules = topological_sort(modules)

    supported, default = _load_i18n_settings_from_env()
    extra = _discover_extra_locale_sources()

    diagnostics = run_diagnostics(
        modules,
        i18n_supported_locales=supported,
        i18n_default_locale=default,
        i18n_extra_sources=extra,
    )
    print_diagnostics(diagnostics)

    errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
