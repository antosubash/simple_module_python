"""Every "Recent migrations" row carries a module chip, labelled or not.

Only a module's *first* migration carries an Alembic branch label — that is
the convention this project migrates under — so every later revision reached
the screen with a blank chip, which reads as a missing value rather than as
"this one is the host's". ``list_migrations`` still refuses to guess: a wrong
branch label would corrupt a ``downgrade <module>@base``, while a wrong word
in a list costs nothing.
"""

from __future__ import annotations

from dashboard.doctor import HOST_MIGRATION_CHIP, _module_chip


class TestMigrationChips:
    def test_a_message_naming_a_module_takes_that_chip(self) -> None:
        packages = {"users", "audit_log", "keycloak"}
        assert _module_chip("users oauth_account", packages) == "users"
        assert _module_chip("keycloak initial schema", packages) == "keycloak"

    def test_a_module_named_mid_message_still_counts(self) -> None:
        assert _module_chip("add audit_log tables", {"users", "audit_log"}) == "audit_log"

    def test_a_table_name_resolves_to_its_module(self) -> None:
        assert _module_chip("users_user lower(email) index", {"users"}) == "users"

    def test_a_message_naming_nothing_belongs_to_the_host(self) -> None:
        assert _module_chip("initial schema", {"users"}) == HOST_MIGRATION_CHIP
        assert _module_chip("", {"users"}) == HOST_MIGRATION_CHIP
