"""Regenerate the typed i18n key files without booting the host. `make gen-i18n`."""

import logging
from pathlib import Path

from simple_module_core.discovery import discover_modules
from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
from simple_module_hosting.settings import Settings

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    # i18n_manifest logs one INFO line per file it actually writes. Without a
    # handler those lines are below the root logger's default threshold, and the
    # script's own closing line reads identically whether it regenerated both
    # files or wrote nothing at all. Scoped to that one logger: the root stays at
    # WARNING so discovery's per-module chatter doesn't bury the two lines that
    # answer the question this command was run to ask.
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("simple_module_hosting.i18n_manifest").setLevel(logging.INFO)
    # Env-only Settings() — no merge_host_settings, so a DB-stored
    # i18n_default_locale override is invisible here. Accepted trade-off for a
    # tool that must not boot the app (and thus must not touch the DB).
    settings = Settings()
    # Mirrors create_app's discovery call (app_builder.py) so the key union
    # this emits always matches what a live boot would type: if an operator
    # restricts modules via SM_MODULES_ENABLED, the generated keys track that
    # same subset rather than drifting to "every installed module" while the
    # running app types fewer.
    modules = discover_modules(enabled=settings.modules_enabled, strict=not settings.is_development)
    # strict: a live boot prefers stale types to a failed start, but this command
    # exists only to write those files. Failing here beats handing `tsc` a stale
    # union and letting it report a missing key that the catalog does contain.
    emit_frontend_types_for_modules(settings, modules, ROOT, strict=True)
    print("i18n key files up to date")
