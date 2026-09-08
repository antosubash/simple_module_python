"""Every activity line comes out of a catalog, not out of an f-string.

The card used to build its sentences in Python — ``f"{verb} {kind} {label}"``
from an English verb table — so the "Recent activity" list read as English in
every locale and no translation could reach it. Neither lint check could see
it: they only parse ``.tsx``.

These tests translate with a stub that echoes ``key(args)`` instead of copy, so
an assertion here fails the moment a sentence is assembled locally again — an
f-string would produce prose where the stub produces a key.
"""

from __future__ import annotations

from typing import Any

from simple_module_core import AuditLink, AuditLinkRegistry
from users.admin.recent_activity import _kind_of, _summarise


class _EchoTranslator:
    """Stands in for ``Translator``, rendering the key and its arguments."""

    def t(self, key: str, **params: Any) -> str:
        rendered = ", ".join(f"{name}={value}" for name, value in sorted(params.items()))
        return f"{key}({rendered})"


class _KeylessTranslator(_EchoTranslator):
    """A translator with an empty catalog: ``t`` echoes the key back."""

    def t(self, key: str, **params: Any) -> str:
        return key


T = _EchoTranslator()


class TestSummaryKeys:
    def test_a_create_reads_from_the_created_key(self) -> None:
        assert _summarise(T, "create", "setting", "smtp_host", []) == (
            "users.recent_activity.summary.created(kind=setting, label=smtp_host)"
        )

    def test_every_spelling_of_one_action_shares_a_key(self) -> None:
        """Writers disagree on "delete"/"deleted"; the reader should not."""
        assert _summarise(T, "delete", "file", "x", []) == _summarise(T, "deleted", "file", "x", [])

    def test_an_unknown_action_keeps_its_verb_as_an_argument(self) -> None:
        """Inventing a translation for a verb only one writer uses is a guess."""
        assert _summarise(T, "archive", "file", "x", []) == (
            "users.recent_activity.summary.other(action=Archive, kind=file, label=x)"
        )

    def test_named_fields_are_one_argument_not_a_locally_joined_sentence(self) -> None:
        summary = _summarise(T, "update", "user", "Ada", [{"field": "email"}, {"field": "roles"}])
        assert summary == (
            "users.recent_activity.summary.changed_fields(fields=email, roles, label=Ada)"
        )

    def test_a_long_field_list_becomes_a_count(self) -> None:
        changes = [{"field": name} for name in ("a", "b", "c", "d")]
        assert _summarise(T, "update", "user", "Ada", changes) == (
            "users.recent_activity.summary.changed_count(count=4, label=Ada)"
        )

    def test_an_update_with_no_recorded_fields_falls_back_to_the_plain_verb(self) -> None:
        assert _summarise(T, "update", "user", "Ada", None) == (
            "users.recent_activity.summary.updated(kind=user, label=Ada)"
        )

    def test_a_missing_catalog_entry_leaves_no_trailing_space(self) -> None:
        """The key echoes back verbatim; nothing here appends a stray gap."""
        assert _summarise(_KeylessTranslator(), "create", "setting", "x", []) == (
            "users.recent_activity.summary.created"
        )


class TestKindOf:
    def _registry(self, link: AuditLink) -> AuditLinkRegistry:
        registry = AuditLinkRegistry()
        registry.register(link)
        return registry

    def test_the_links_label_key_is_translated(self) -> None:
        registry = self._registry(
            AuditLink(
                entity_type="Setting",
                url_template="/s/{id}",
                label="Setting",
                label_key="settings.audit.setting",
            )
        )
        assert _kind_of(T, registry, "Setting") == "settings.audit.setting()"

    def test_an_unresolved_key_falls_back_to_the_english_label(self) -> None:
        registry = self._registry(
            AuditLink(
                entity_type="Setting",
                url_template="/s/{id}",
                label="Setting",
                label_key="settings.audit.setting",
            )
        )
        assert _kind_of(_KeylessTranslator(), registry, "Setting") == "setting"

    def test_a_type_no_module_claims_reads_as_its_class_name(self) -> None:
        assert _kind_of(T, AuditLinkRegistry(), "Unclaimed") == "unclaimed"

    def test_no_registry_at_all_is_survivable(self) -> None:
        assert _kind_of(T, None, "Unclaimed") == "unclaimed"
