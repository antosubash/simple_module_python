"""Tests for AuditLink / AuditLinkRegistry.

The audit log stores a table name and a primary key. This registry is how a
module says where those rows can be opened, so the log stops being a wall of
unactionable uuids.
"""

from __future__ import annotations

import pytest
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry


class TestAuditLink:
    def test_url_for_substitutes_the_id(self):
        link = AuditLink(entity_type="User", url_template="/users/admin/{id}")
        assert link.url_for("a91f3c2b") == "/users/admin/a91f3c2b"

    def test_template_without_placeholder_is_rejected(self):
        """Every row would otherwise link to the same page."""
        with pytest.raises(ValueError, match="contains no"):
            AuditLink(entity_type="User", url_template="/users/admin")

    def test_label_defaults_to_empty(self):
        assert AuditLink(entity_type="t", url_template="/t/{id}").label == ""


class TestAuditLinkRegistry:
    def test_get_returns_none_for_unclaimed_tables(self):
        """Join tables and blob stores have no screen; that is not an error."""
        assert AuditLinkRegistry().get("UserPermission") is None

    def test_register_and_get(self):
        reg = AuditLinkRegistry()
        link = AuditLink(entity_type="User", url_template="/users/admin/{id}", label="User")
        reg.register(link)
        assert reg.get("User") is link

    def test_conflicting_claims_raise(self):
        """Two modules mapping one table means one of them silently loses."""
        reg = AuditLinkRegistry()
        reg.register(AuditLink(entity_type="User", url_template="/a/{id}"))
        with pytest.raises(ValueError, match="Two modules claim"):
            reg.register(AuditLink(entity_type="User", url_template="/b/{id}"))

    def test_registering_the_same_link_twice_is_allowed(self):
        """Idempotent re-registration must not break a re-entrant boot."""
        reg = AuditLinkRegistry()
        for _ in range(2):
            reg.register(AuditLink(entity_type="User", url_template="/a/{id}"))
        assert len(reg.all_links) == 1

    def test_all_links_is_a_copy(self):
        reg = AuditLinkRegistry()
        reg.register(AuditLink(entity_type="User", url_template="/a/{id}"))
        reg.all_links.clear()
        assert reg.get("User") is not None
