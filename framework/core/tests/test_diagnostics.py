"""Tests for MigrationDiagnostics and print_diagnostics output."""

from __future__ import annotations

from simple_module_core.diagnostics import (
    Diagnostic,
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
)


class TestMigrationDiagnostics:
    async def test_sm010_migration_mismatch(self):
        """SM010 should fire when current revision != head."""
        diag = MigrationDiagnostics()
        results = diag.check_revision_mismatch(
            current_revision="abc123",
            head_revision="def456",
        )
        assert len(results) == 1
        assert results[0].code == "SM010"
        assert results[0].level == DiagnosticLevel.ERROR

    async def test_sm010_no_error_when_current(self):
        """SM010 should not fire when DB is at head."""
        diag = MigrationDiagnostics()
        results = diag.check_revision_mismatch(
            current_revision="abc123",
            head_revision="abc123",
        )
        assert len(results) == 0

    async def test_sm011_missing_tables(self):
        """SM011 should fire when module tables aren't in migration tables."""
        diag = MigrationDiagnostics()
        results = diag.check_table_coverage(
            module_tables={"products_product", "products_category"},
            migrated_tables={"products_product"},
        )
        assert len(results) == 1
        assert results[0].code == "SM011"
        assert results[0].level == DiagnosticLevel.WARNING
        assert "products_category" in results[0].message

    async def test_sm011_no_warning_when_covered(self):
        """SM011 should not fire when all tables are covered."""
        diag = MigrationDiagnostics()
        results = diag.check_table_coverage(
            module_tables={"products_product"},
            migrated_tables={"products_product"},
        )
        assert len(results) == 0


class TestPrintDiagnostics:
    async def test_writes_to_stderr(self, capsys):
        diag = Diagnostic(
            level=DiagnosticLevel.ERROR,
            code="SM001",
            message="test error",
            module_name="TestMod",
        )
        print_diagnostics([diag])
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "SM001" in captured.err
        assert "Results: 1 error(s)" in captured.err

    async def test_empty_is_quiet(self, capsys):
        print_diagnostics([])
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestAuthProviderDiagnostics:
    def test_sm020_multiple_auth_providers(self):
        from simple_module_core.diagnostics._module import ModuleDiagnostics
        from simple_module_core.module import ModuleBase, ModuleMeta

        class FakeUsers(ModuleBase):
            meta = ModuleMeta(name="Users")
            _is_auth_provider = True

        class FakeKeycloak(ModuleBase):
            meta = ModuleMeta(name="Keycloak")
            _is_auth_provider = True

        diags = ModuleDiagnostics()
        results = diags._check_auth_provider_conflict([FakeUsers(), FakeKeycloak()])
        assert len(results) == 1
        assert results[0].code == "SM020"
        assert results[0].level == DiagnosticLevel.ERROR

    def test_sm021_no_auth_provider(self):
        from simple_module_core.diagnostics._module import ModuleDiagnostics
        from simple_module_core.module import ModuleBase, ModuleMeta

        class FakeDashboard(ModuleBase):
            meta = ModuleMeta(name="Dashboard")

        diags = ModuleDiagnostics()
        results = diags._check_auth_provider_conflict([FakeDashboard()])
        assert len(results) == 1
        assert results[0].code == "SM021"
        assert results[0].level == DiagnosticLevel.WARNING

    def test_single_provider_passes(self):
        from simple_module_core.diagnostics._module import ModuleDiagnostics
        from simple_module_core.module import ModuleBase, ModuleMeta

        class FakeUsers(ModuleBase):
            meta = ModuleMeta(name="Users")
            _is_auth_provider = True

        class FakeDashboard(ModuleBase):
            meta = ModuleMeta(name="Dashboard")

        diags = ModuleDiagnostics()
        results = diags._check_auth_provider_conflict([FakeUsers(), FakeDashboard()])
        assert results == []
