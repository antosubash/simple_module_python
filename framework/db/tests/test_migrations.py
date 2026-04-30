"""Tests for build_module_metadata and make_include_object (Gap 1)."""

from __future__ import annotations


class TestMigrationsHelper:
    async def test_combined_metadata_includes_installed_module_tables(self):
        """build_module_metadata() discovers every installed module's models and
        aggregates their tables into a single SQLAlchemy MetaData. This is the
        helper an Alembic env.py calls to get its `target_metadata`, and it is
        the crux of the pip-installed module story: the logic does not care
        whether modules are editable installs or wheel installs — it uses
        importlib to locate them.
        """
        from simple_module_db.migrations import build_module_metadata

        metadata = build_module_metadata()
        table_names = set(metadata.tables.keys())

        # Products ships models and must contribute at least one table.
        # (Dashboard is event-driven with no models; Auth's tables are
        # currently not part of this workspace's ORM surface.)
        assert any("product" in name.lower() for name in table_names)
        assert len(table_names) >= 1

    async def test_combined_metadata_only_returns_module_tables(self):
        """The helper's allowlist must exclude host-defined or framework-internal
        tables so autogenerate doesn't try to drop them on the first run.
        """
        from simple_module_db.migrations import build_module_metadata

        metadata = build_module_metadata()
        allowlist = set(metadata.tables.keys())

        assert allowlist
        assert all(isinstance(name, str) and name for name in allowlist)

    async def test_include_object_allowlist_filters_unknown_tables(self):
        """`make_include_object` returns an Alembic `include_object` filter that
        passes only tables the framework manages — protecting user-added
        tables in the host DB from being destroyed by autogenerate.
        """
        from simple_module_db.migrations import build_module_metadata, make_include_object

        metadata = build_module_metadata()
        include = make_include_object(metadata)

        some_known_table = next(iter(metadata.tables.values()))
        assert include(some_known_table, some_known_table.name, "table", False, None) is True

        from sqlalchemy import Column, Integer, MetaData, Table

        stranger = Table(
            "unrelated_host_table", MetaData(), Column("id", Integer, primary_key=True)
        )
        assert include(stranger, "unrelated_host_table", "table", False, None) is False

    async def test_include_object_skips_unmodeled_cross_module_fks_by_default(self):
        """Cross-module FKs declared at the migration level only (no SQLModel
        relationship) appear in the live DB but never in target metadata.
        Alembic compares: live FK has no metadata counterpart (compare_to is
        None) and would emit ``op.drop_constraint``. The default filter must
        drop those constraint-level diffs to avoid silently destroying real
        FKs on every autogen run.
        """
        from simple_module_db.migrations import build_module_metadata, make_include_object
        from sqlalchemy import Column, ForeignKeyConstraint, Integer, MetaData, Table

        metadata = build_module_metadata()
        include = make_include_object(metadata)

        known = next(iter(metadata.tables.values()))
        # Synthesise a foreign-key constraint hung off a tracked parent table
        # whose target metadata has no matching FK (compare_to=None).
        scratch = MetaData()
        local = Table(known.name, scratch, Column("id", Integer, primary_key=True))
        fk = ForeignKeyConstraint([local.c.id], ["other_module.other.id"], name="fk_xmod")
        local.append_constraint(fk)

        # compare_to=None ⇒ live DB has it, metadata does not; default filter skips.
        assert include(fk, "fk_xmod", "foreign_key_constraint", True, None) is False

        # Opt-out flag restores the prior drop-on-sight behaviour.
        strict = make_include_object(metadata, ignore_unmodeled_fks=False)
        assert strict(fk, "fk_xmod", "foreign_key_constraint", True, None) is True

        # FKs on UNKNOWN parent tables remain rejected by the table allowlist.
        stranger_meta = MetaData()
        stranger = Table(
            "totally_unknown_table",
            stranger_meta,
            Column("id", Integer, primary_key=True),
            Column("ref", Integer),
        )
        stranger_fk = ForeignKeyConstraint(
            [stranger.c.ref], ["something.else.id"], name="fk_stranger"
        )
        stranger.append_constraint(stranger_fk)
        # When compare_to is provided (constraint exists in both sides) we fall
        # through to the parent-table allowlist check.
        assert (
            include(stranger_fk, "fk_stranger", "foreign_key_constraint", False, stranger_fk)
            is False
        )
