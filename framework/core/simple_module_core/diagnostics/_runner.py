"""Entry points that assemble and print diagnostic output."""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._db_extensions import check_db_extensions_need_postgres
from simple_module_core.diagnostics._expression_index import (
    check_expression_indexes_unverifiable,
    module_all_tables,
)
from simple_module_core.diagnostics._migration import MigrationDiagnostics
from simple_module_core.diagnostics._module import ModuleDiagnostics
from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)
_printed_diagnostics: set[tuple[int, str, str, str, str | None]] = set()


def run_diagnostics(
    modules: list[ModuleBase],
    *,
    migration_state: dict | None = None,
    module_tables: set[str] | None = None,
    migrated_tables: set[str] | None = None,
    i18n_supported_locales: list[str] | None = None,
    i18n_default_locale: str | None = None,
    i18n_extra_sources: list[tuple[str, str, Path]] | None = None,
    database_dialect: str | None = None,
    i18n_unknown_overrides: dict[str, list[str]] | None = None,
    existing_index_names: frozenset[str] | None = None,
) -> list[Diagnostic]:
    """Convenience function to run all diagnostics.

    When ``migration_state`` is provided, also runs migration diagnostics.
    ``i18n_default_locale`` turns on the locale checks; ``i18n_supported_locales``
    is the declared locale set, and leaving it empty runs those checks against
    whatever locale files are on disk instead of skipping them entirely (see
    :class:`I18nDiagnostics`). ``i18n_extra_sources`` lets callers include
    host/ui locale dirs that aren't owned by a ``ModuleBase``.
    ``database_dialect`` (``"sqlite"``, ``"postgresql"``...) enables SM026, which
    flags expression indexes a SQLite database cannot verify, and SM029, which flags
    modules declaring ``db_extensions`` on SQLite. ``existing_index_names``
    (``sqlite_file_index_names``) limits SM026 to indexes the database lacks.
    ``i18n_unknown_overrides`` (``I18nRegistry.unknown_override_keys``) enables SM027.
    """
    diagnostics = ModuleDiagnostics().run(modules)

    if database_dialect is not None:
        for mod in modules:
            diagnostics.extend(
                check_expression_indexes_unverifiable(
                    module_all_tables(mod),
                    database_dialect,
                    mod.meta.name,
                    existing_index_names=existing_index_names,
                )
            )
            diagnostics.extend(check_db_extensions_need_postgres(mod, database_dialect))

    if i18n_default_locale:
        from simple_module_core.diagnostics._i18n import I18nDiagnostics

        diagnostics.extend(
            I18nDiagnostics(
                supported_locales=i18n_supported_locales or None,
                default_locale=i18n_default_locale,
                extra_sources=i18n_extra_sources,
            ).run(modules)
        )

    if i18n_unknown_overrides:
        from simple_module_core.diagnostics._i18n import check_unknown_overrides

        diagnostics.extend(check_unknown_overrides(i18n_unknown_overrides))

    if migration_state is not None:
        migration_diag = MigrationDiagnostics()
        diagnostics.extend(
            migration_diag.check_revision_mismatch(
                current_revision=migration_state.get("current_revision"),
                head_revision=migration_state.get("head_revision"),
            )
        )
        if module_tables is not None and migrated_tables is not None:
            diagnostics.extend(migration_diag.check_table_coverage(module_tables, migrated_tables))

    return diagnostics


def print_diagnostics(diagnostics: list[Diagnostic], *, once: bool = False) -> None:
    """Print diagnostics to the current stderr, optionally once per process at boot.

    Output is best-effort: a slow or closed stderr must never prevent boot.
    The PID in the key keeps forked serving processes independent of parents.
    Doctor calls leave ``once`` disabled so every invocation prints a full report.
    """
    if not diagnostics:
        with suppress(OSError):
            logger.info("\u2713 No module diagnostics issues found")
        return

    unique = []
    for d in diagnostics:
        if once:
            key = (os.getpid(), d.code, d.message, d.module_name, d.file)
            if key in _printed_diagnostics:
                continue
            _printed_diagnostics.add(key)
        unique.append(d)
    if not unique:
        return

    levels = Counter(d.level for d in unique)
    codes = Counter(d.code for d in unique)
    summary = (
        f"Results: {levels[DiagnosticLevel.ERROR]} error(s), "
        f"{levels[DiagnosticLevel.WARNING]} warning(s), {levels[DiagnosticLevel.INFO]} info; "
        + ", ".join(f"{code}={count}" for code, count in sorted(codes.items()))
    )
    report = "".join(f"{d}\n\n" for d in unique) + summary + "\n"
    try:
        _write_report(report)
    except OSError as exc:
        # A logging handler may itself target the same broken stderr pipe.
        with suppress(OSError):
            logger.warning("Could not write module diagnostics (%s); %s", exc, summary)


def _write_report(report: str) -> None:
    """Retry partial writes and flushes for at most 100 ms per report."""
    # CliRunner and pytest replace stderr after this module is imported.
    stream = sys.stderr
    deadline = time.monotonic() + 0.1
    position = 0
    while True:
        try:
            while position < len(report):
                written = stream.write(report[position:])
                if written == 0:
                    raise BlockingIOError("stderr made no progress")
                position += written
            stream.flush()
            return
        except BlockingIOError as exc:
            position += getattr(exc, "characters_written", 0)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))
