"""The generated key union must cover every *installed* module.

`make lint` runs `tsc -p modules/<name>` for each module in the workspace,
including the auth provider this host does not activate. Those pages still
call `t(keys.<namespace>....)`, so a union built from the booted (auth-filtered)
module list fails their build with keys that "do not exist" — while the app
itself runs fine, which makes it a confusing thing to debug.

Generation therefore runs over the unfiltered module list; the runtime registry
stays filtered, so an inactive module's strings are typed but never served.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_core.discovery import discover_modules
from simple_module_hosting.i18n_manifest import build_i18n_registry
from simple_module_hosting.settings import Settings

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_KEYS_FILE = _PROJECT_ROOT / "packages" / "i18n" / "src" / "keys.generated.ts"


def _namespaces_of(module) -> list[str]:
    try:
        return list(module.locale_dirs().keys())
    except Exception:
        return []


@pytest.mark.skipif(not _KEYS_FILE.is_file(), reason="source checkout only")
def test_every_installed_module_namespace_is_in_the_generated_keys() -> None:
    modules = discover_modules()
    text = _KEYS_FILE.read_text(encoding="utf-8")

    missing = []
    for module in modules:
        for namespace in _namespaces_of(module):
            # Top-level entries are emitted as `  <namespace>: {`.
            if f"\n  {namespace}: {{" not in text:
                missing.append(namespace)

    assert not missing, (
        f"keys.generated.ts is missing namespaces {sorted(missing)}. "
        "Regenerate it from the unfiltered installed-module list "
        "(booting the host in development does this)."
    )


@pytest.mark.skipif(not _KEYS_FILE.is_file(), reason="source checkout only")
def test_generation_over_installed_modules_includes_inactive_auth_providers() -> None:
    """Guards the app_builder call site against being handed the booted list."""
    modules = discover_modules()
    providers = [m for m in modules if "keycloak" in _namespaces_of(m)]
    if not providers:
        pytest.skip("keycloak module not installed in this workspace")

    settings = Settings()
    registry, _ = build_i18n_registry(settings, modules, _PROJECT_ROOT)
    keys = registry.messages(settings.i18n_default_locale)
    assert any(k.startswith("keycloak.") for k in keys), (
        "an installed-but-inactive auth provider contributed no keys; "
        "its pages would fail to typecheck"
    )
