"""Regenerate the typed i18n key files without booting the host. `make gen-i18n`."""

from pathlib import Path

from simple_module_core.discovery import discover_modules
from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
from simple_module_hosting.settings import Settings

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    emit_frontend_types_for_modules(Settings(), discover_modules(), ROOT)
    print("i18n key files regenerated")
