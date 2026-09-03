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


class TestTableName:
    """The audit row's type tag shows the table the row lives in.

    ``entity_type`` is the model class name — the audit trail records
    ``type(obj).__name__`` — but ``User`` is jargon and ``users_user`` is what
    an operator reading a migration or a psql prompt already knows. The two
    cannot be derived from one another, so the module that owns the table says
    both.
    """

    def test_table_name_defaults_to_none(self):
        assert AuditLink(entity_type="User", url_template="/u/{id}").table_name is None

    def test_table_name_round_trips(self):
        link = AuditLink(entity_type="User", url_template="/u/{id}", table_name="users_user")
        assert link.table_name == "users_user"


class TestLabelResolver:
    """A row's *display name* is the owning module's business.

    The registry cannot know that a ``Setting`` is named by its ``key`` and a
    ``User`` by ``full_name or email``, and the audit log must not grow an
    import of every module to find out. The owner supplies a batch resolver
    instead: one call per entity type per page, never one query per row.
    """

    def test_label_resolver_defaults_to_none(self):
        assert AuditLink(entity_type="User", url_template="/u/{id}").label_resolver is None

    async def test_resolver_is_stored_and_callable(self):
        async def resolve(_db, ids):
            return {i: f"name-{i}" for i in ids}

        link = AuditLink(entity_type="User", url_template="/u/{id}", label_resolver=resolve)
        assert link.label_resolver is not None
        assert await link.label_resolver(None, ["a"]) == {"a": "name-a"}

    def test_registering_twice_with_distinct_closures_is_idempotent(self):
        """A resolver is a closure, so two boots build two unequal objects.

        Comparing on it would turn a re-entrant boot into "Two modules claim
        User" — a conflict is about two modules pointing one entity type at
        two different screens, which the identity fields already express.
        """
        reg = AuditLinkRegistry()
        for _ in range(2):
            reg.register(
                AuditLink(
                    entity_type="User",
                    url_template="/a/{id}",
                    label_resolver=lambda _db, ids: None,
                )
            )
        assert len(reg.all_links) == 1

    def test_genuinely_conflicting_claims_still_raise(self):
        reg = AuditLinkRegistry()
        reg.register(AuditLink(entity_type="User", url_template="/a/{id}"))
        with pytest.raises(ValueError, match="Two modules claim"):
            reg.register(
                AuditLink(
                    entity_type="User", url_template="/b/{id}", label_resolver=lambda *_: None
                )
            )
