"""Regenerate the typed i18n key files without booting the host. `make gen-i18n`."""

from pathlib import Path

from simple_module_core.discovery import discover_modules
from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
from simple_module_hosting.settings import Settings

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
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
    emit_frontend_types_for_modules(settings, modules, ROOT)
    print("i18n key files regenerated")
