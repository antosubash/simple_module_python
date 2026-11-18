"""Tests for create_module_base, detect_provider, and mixin field surfaces."""

from __future__ import annotations

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider


class TestCreateModuleBase:
    async def test_returns_declarative_base(self):
        base = create_module_base("test_mod_base")
        assert hasattr(base, "metadata")
        assert base.__abstract__ is True

    async def test_metadata_has_no_schema(self):
        base = create_module_base("noschemod")
        assert base.metadata.schema is None

    async def test_caching_same_name(self):
        base1 = create_module_base("cache_test")
        base2 = create_module_base("cache_test")
        assert base1 is base2

    async def test_module_name_stored(self):
        base = create_module_base("named_mod")
        assert base.__module_name__ == "named_mod"

    async def test_all_module_bases_is_deduped(self):
        """Re-creating the same module must not grow ``all_module_bases``."""
        from simple_module_db import base as base_mod

        create_module_base("dedupe_test")
        before = len(base_mod.all_module_bases)

        create_module_base("dedupe_test")
        after = len(base_mod.all_module_bases)

        assert after == before
        assert create_module_base("dedupe_test") in base_mod.all_module_bases


class TestDetectProvider:
    @pytest.mark.parametrize("dialect", ["sqlite", "sqlite+aiosqlite", "sqlite+pysqlite"])
    def test_sqlite(self, dialect):
        assert detect_provider(f"{dialect}:///:memory:") == DatabaseProvider.SQLITE

    @pytest.mark.parametrize(
        "dialect",
        [
            "postgresql",
            "postgresql+asyncpg",
            "postgresql+psycopg",
            "postgresql+psycopg2",
            pytest.param("postgres", id="legacy-alias"),
        ],
    )
    def test_postgresql(self, dialect):
        assert detect_provider(f"{dialect}://user:pass@localhost/db") == DatabaseProvider.POSTGRESQL

    @pytest.mark.parametrize("dialect", ["mysql", "mysql+aiomysql", "mssql+pyodbc", "postgresish"])
    def test_unsupported_dialect_does_not_expose_credentials(self, dialect):
        with pytest.raises(ValueError) as error:
            detect_provider(f"{dialect}://user:private-password@localhost/db")
        message = str(error.value)
        assert dialect.split("+")[0] in message
        assert "sqlite" in message.lower() and "postgresql" in message.lower()
        assert "private-password" not in message
        assert "user" not in message


class TestMixins:
    async def test_audit_mixin_fields(self):
        """AuditMixin should define created_at, updated_at, created_by, updated_by."""
        fields = ["created_at", "updated_at", "created_by", "updated_by"]
        for field_name in fields:
            assert field_name in AuditMixin.model_fields, f"AuditMixin missing {field_name}"

    async def test_soft_delete_mixin_fields(self):
        """SoftDeleteMixin should define is_deleted, deleted_at, deleted_by."""
        fields = ["is_deleted", "deleted_at", "deleted_by"]
        for field_name in fields:
            assert field_name in SoftDeleteMixin.model_fields, (
                f"SoftDeleteMixin missing {field_name}"
            )

    async def test_versioned_mixin_fields(self):
        assert "version" in VersionedMixin.model_fields

    async def test_multi_tenant_mixin_fields(self):
        """MultiTenantMixin should define tenant_id."""
        assert "tenant_id" in MultiTenantMixin.model_fields
