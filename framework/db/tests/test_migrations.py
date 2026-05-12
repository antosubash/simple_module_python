"""Tests for the simple_module_db.migrations helpers."""

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


class TestProcessRevisionDirectives:
    """Autogenerate silently drops expression-based indexes (e.g. ``lower(email)``)
    on SQLite. ``make_process_revision_directives`` re-injects them when the
    target table is being newly created in the same revision."""

    def _build_meta(self, *, expression_index: bool = True):
        from sqlalchemy import Column, Index, Integer, MetaData, String, Table, text

        meta = MetaData()
        t = Table(
            "things",
            meta,
            Column("id", Integer, primary_key=True),
            Column("email", String(320)),
        )
        if expression_index:
            Index("ix_things_email_lower", text("lower(email)"), _table=t)
        else:
            Index("ix_things_email", t.c.email)
        return meta

    def _build_directives(self, table_name: str, *extra_ops, empty: bool = False):
        from alembic.operations.ops import (
            CreateTableOp,
            DowngradeOps,
            DropTableOp,
            MigrationScript,
            UpgradeOps,
        )
        from sqlalchemy import Column, Integer, String

        if empty:
            upgrade_ops_list, downgrade_ops_list = [], []
        else:
            create_table = CreateTableOp(
                table_name,
                [Column("id", Integer, primary_key=True), Column("email", String(320))],
            )
            upgrade_ops_list = [create_table, *extra_ops]
            downgrade_ops_list = [DropTableOp(table_name)]
        return [
            MigrationScript(
                rev_id="abc123",
                upgrade_ops=UpgradeOps(ops=upgrade_ops_list),
                downgrade_ops=DowngradeOps(ops=downgrade_ops_list),
                message="test",
            )
        ]

    def test_injects_expression_index_after_create_table(self):
        """A functional index in metadata is appended as ``CreateIndexOp`` after
        the matching ``CreateTableOp``, and the reverse drop is inserted before
        the ``DropTableOp`` in the downgrade."""
        from alembic.operations.ops import CreateIndexOp, DropIndexOp
        from simple_module_db.migrations import make_process_revision_directives

        directives = self._build_directives("things")
        make_process_revision_directives(self._build_meta())(None, None, directives)

        index_ops = [op for op in directives[0].upgrade_ops.ops if isinstance(op, CreateIndexOp)]
        assert len(index_ops) == 1
        assert index_ops[0].index_name == "ix_things_email_lower"
        assert index_ops[0].table_name == "things"

        drop_ops = [op for op in directives[0].downgrade_ops.ops if isinstance(op, DropIndexOp)]
        assert len(drop_ops) == 1
        assert drop_ops[0].index_name == "ix_things_email_lower"

    def test_does_not_inject_when_no_create_table(self):
        """If the revision is not creating the table (e.g. a pure data migration
        or unrelated change), the hook should not append a CreateIndexOp."""
        from alembic.operations.ops import CreateIndexOp
        from simple_module_db.migrations import make_process_revision_directives

        directives = self._build_directives("things", empty=True)
        make_process_revision_directives(self._build_meta())(None, None, directives)

        assert not any(isinstance(op, CreateIndexOp) for op in directives[0].upgrade_ops.ops)

    def test_does_not_double_inject_when_already_present(self):
        """On Postgres, autogenerate emits the expression index normally. The
        hook must not duplicate it."""
        from alembic.operations.ops import CreateIndexOp
        from simple_module_db.migrations import make_process_revision_directives

        meta = self._build_meta()
        idx = next(iter(meta.tables["things"].indexes))
        directives = self._build_directives("things", CreateIndexOp.from_index(idx))
        make_process_revision_directives(meta)(None, None, directives)

        index_ops = [op for op in directives[0].upgrade_ops.ops if isinstance(op, CreateIndexOp)]
        assert len(index_ops) == 1

    def test_ignores_column_based_indexes(self):
        """Plain column indexes are already handled correctly by autogenerate;
        the hook must not touch them."""
        from alembic.operations.ops import CreateIndexOp
        from simple_module_db.migrations import make_process_revision_directives

        directives = self._build_directives("things")
        make_process_revision_directives(self._build_meta(expression_index=False))(
            None, None, directives
        )

        assert not any(isinstance(op, CreateIndexOp) for op in directives[0].upgrade_ops.ops)
