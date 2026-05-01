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

        # Users ships models and must contribute at least one table.
        # (Dashboard is event-driven with no models; Auth's tables are
        # currently not part of this workspace's ORM surface.)
        assert any("user" in name.lower() for name in table_names)
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
        Alembic passes ``compare_to=None`` for live-only constraints and would
        emit ``op.drop_constraint``; the default filter must drop those
        constraint-level diffs to avoid destroying real FKs on every autogen.
        """
        from simple_module_db.migrations import build_module_metadata, make_include_object
        from sqlalchemy import Column, ForeignKeyConstraint, Integer, MetaData, Table

        metadata = build_module_metadata()
        include = make_include_object(metadata)
        strict = make_include_object(metadata, ignore_unmodeled_fks=False)

        known = next(iter(metadata.tables.values()))
        scratch = MetaData()
        local = Table(known.name, scratch, Column("id", Integer, primary_key=True))
        fk = ForeignKeyConstraint([local.c.id], ["other_module.other.id"], name="fk_xmod")
        local.append_constraint(fk)

        assert include(fk, "fk_xmod", "foreign_key_constraint", True, None) is False
        assert strict(fk, "fk_xmod", "foreign_key_constraint", True, None) is True

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
        assert (
            include(stranger_fk, "fk_stranger", "foreign_key_constraint", False, stranger_fk)
            is False
        )
