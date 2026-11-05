"""Durable event keys and handler names are wire names: freeze them.

Outbox rows are keyed by the event's ``module.qualname`` and the handler's
name (its import path unless ``name=`` is given). Moving either to another
module (docs/module-layout.md) strands every undelivered row: it retries as an
unknown handler, then goes ``dead``. A move must pin the old name with
``subscribe_durable(..., name=...)``; a changed entry here is a data migration,
not a refactor.
"""

from __future__ import annotations

from simple_module_core.discovery import discover_modules
from simple_module_core.events import EventBus

_TENANT_DELETED = "simple_module_core.tenant_events.TenantDeleted"
_USER_DELETED = "simple_module_core.user_events.UserDeleted"

EXPECTED: dict[str, frozenset[str]] = {
    "file_storage.tenant_deletion.TenantStorageCleanupRequested": frozenset(
        {"file_storage.tenant_deletion.purge_objects"}
    ),
    _TENANT_DELETED: frozenset(
        {
            "api_tokens.tenant_cleanup.purge_tenant_data",
            "feature_flags.tenant_cleanup.purge_tenant_data",
            "file_storage.tenant_deletion.purge_rows",
            "sharing.tenant_cleanup.purge_tenant_data",
        }
    ),
    _USER_DELETED: frozenset(
        {
            "api_tokens.user_cleanup.purge_user_tokens",
            "permissions.user_cleanup.purge_user_grants",
            "sharing.user_cleanup.purge_user_shares",
            "tenants.user_cleanup.purge_user_memberships",
        }
    ),
    "tenants.contracts.events.InvitationCreated": frozenset({"tenants.send_invitation_email"}),
}


def _registered() -> dict[str, frozenset[str]]:
    bus = EventBus()
    for module in discover_modules():
        # The worker registers durable handlers the same way, with no app.
        module.register_event_handlers(bus, None)
    return {key: frozenset(by_name) for key, by_name in bus.durable._subs.items()}


def test_durable_wire_names_are_unchanged() -> None:
    assert _registered() == EXPECTED
