"""Role recipient searches match the labels shown in the active locale (#963)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sharing
from _sharing_support import NOTE_TYPE, FakeDirectory, register_note_type
from sharing.core.service import SharingService
from simple_module_core.i18n import I18nRegistry, Translator
from simple_module_core.resources import ResourcePrincipal, ResourceTypeRegistry
from simple_module_core.tenancy import TenantRole, tenant_role
from simple_module_db.tenancy import tenant_context


@pytest.fixture
def role_picker():
    messages = I18nRegistry(default_locale="en", supported_locales=["en", "de"])
    messages.add_source("sharing", Path(sharing.__file__).parent / "locales")
    messages.load()
    registry = ResourceTypeRegistry()
    register_note_type(registry)

    def build(locale):
        translator = Translator(messages, locale=locale, default_locale="en")
        service = SharingService(
            AsyncMock(), registry, FakeDirectory("owner"), translate=translator.t
        )
        service._authorize = AsyncMock(return_value=SimpleNamespace(owner_id="owner"))
        return service

    return build


@pytest.mark.parametrize(
    "locale,query,expected",
    [
        ("en", "Members", ["member"]),
        ("en", "Owners", ["owner"]),
        ("en", "Administrators", ["admin"]),
        ("de", "Mitglieder", ["member"]),
        ("de", "Eigentümer", ["owner"]),
        ("de", "Administratoren", ["admin"]),
        ("en", "  mEmBeRs  ", ["member"]),
        ("de", "EIGENTÜMER", ["owner"]),
        ("de", "Eigentumer", ["owner"]),
        ("de", "Eigentümer", ["owner"]),
        ("de", "glieder", ["member"]),
        ("de", "member", ["member"]),
        ("de", "owner", ["owner"]),
        ("de", "admin", ["admin"]),
        ("en", "Mitglieder", []),
        ("de", "Owners", []),
        ("de", "unknown", []),
    ],
)
async def test_role_candidates_match_ids_and_current_locale_labels(
    role_picker, locale, query, expected
):
    service = role_picker(locale)
    principal = ResourcePrincipal(
        "owner", roles=frozenset({tenant_role(TenantRole.OWNER)}), tenant_id="blue"
    )
    with tenant_context("blue"):
        found = await service.candidates(principal, NOTE_TYPE, "note", query, "tenant_role")
    assert [candidate.id for candidate in found] == expected
    assert all(candidate.subject_type == "tenant_role" for candidate in found)


@pytest.mark.parametrize("tenant_id", [None, "other"])
async def test_localized_role_search_still_requires_active_tenant(role_picker, tenant_id):
    service = role_picker("de")
    principal = ResourcePrincipal(
        "owner", roles=frozenset({tenant_role(TenantRole.OWNER)}), tenant_id=tenant_id
    )
    with tenant_context("blue"):
        assert (
            await service.candidates(principal, NOTE_TYPE, "note", "Mitglieder", "tenant_role")
            == []
        )
