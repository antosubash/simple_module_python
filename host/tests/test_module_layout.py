"""Keep every module package root to the layout in docs/module-layout.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_test.app.layout import assert_module_layout

MODULES = Path(__file__).resolve().parents[2] / "modules"
# Add named domain areas here only when they contain several related features.
DOMAIN_AREAS: dict[str, frozenset[str]] = {
    "api_tokens": frozenset({"credentials"}),
    "audit_log": frozenset({"entries"}),
    "auth": frozenset({"oidc_common"}),
    "background_tasks": frozenset({"executions", "logs", "outbox", "worker"}),
    "branding": frozenset({"assets"}),
    "file_storage": frozenset({"backends", "files", "multipart"}),
    "keycloak": frozenset({"identity"}),
    "mail": frozenset({"delivery"}),
    "oidc": frozenset({"identity"}),
    "permissions": frozenset({"grants"}),
    "settings": frozenset({"module_settings"}),
    "tenants": frozenset({"invitations", "resolution"}),
    "users": frozenset({"accounts", "admin", "auth_local", "demo", "invites", "mailer", "oauth"}),
}


@pytest.mark.parametrize("module", sorted(p.name for p in MODULES.iterdir() if p.is_dir()))
def test_module_root_layout(module: str) -> None:
    assert_module_layout(
        MODULES / module,
        module,
        domain_areas=DOMAIN_AREAS.get(module, frozenset()),
    )
