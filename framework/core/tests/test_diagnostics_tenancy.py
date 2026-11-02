"""SM024 — unique keys on tenant-scoped tables must include tenant_id."""

from __future__ import annotations

from simple_module_core.diagnostics._tenancy import check_tenant_unique_keys
from sqlalchemy import Column, Index, Integer, MetaData, String, Table, UniqueConstraint, func


def _codes(table: Table) -> list[str]:
    return [d.code for d in check_tenant_unique_keys([table], "demo")]


def test_global_unique_column_on_tenant_table_warns():
    t = Table(
        "demo_a",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("tenant_id", String(50)),
        Column("slug", String(50), unique=True),
    )
    assert _codes(t) == ["SM024"]


def test_per_tenant_unique_index_is_fine():
    t = Table(
        "demo_b",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("tenant_id", String(50)),
        Column("slug", String(50)),
        Index("ix_demo_b_tenant_slug", "tenant_id", "slug", unique=True),
        UniqueConstraint("tenant_id", "id"),
    )
    assert _codes(t) == []


def test_unique_index_without_tenant_warns():
    t = Table(
        "demo_c",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("tenant_id", String(50)),
        Column("locale", String(8)),
        Column("slug", String(50)),
        Index("ix_demo_c_locale_slug", "locale", "slug", unique=True),
    )
    diags = check_tenant_unique_keys([t], "demo")
    assert [d.code for d in diags] == ["SM024"]
    assert "ix_demo_c_locale_slug" in diags[0].message


def test_expression_index_counts_as_global():
    t = Table(
        "demo_d",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("tenant_id", String(50)),
        Column("email", String(50)),
    )
    Index("ix_demo_d_email_lower", func.lower(t.c.email), unique=True)
    assert _codes(t) == ["SM024"]


def test_non_tenant_table_is_ignored():
    t = Table(
        "demo_e",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("slug", String(50), unique=True),
    )
    assert _codes(t) == []


def test_module_tables_only_counts_mixin_models(monkeypatch):
    import sys
    import types

    from simple_module_core.diagnostics._tenancy import module_tables

    class MultiTenantMixin:  # stands in for simple_module_db's, matched by name
        pass

    md = MetaData()
    scoped = type(
        "Scoped",
        (MultiTenantMixin,),
        {
            "__table__": Table(
                "demo_scoped",
                md,
                Column("id", Integer, primary_key=True),
                Column("tenant_id", String(5)),
            )
        },
    )
    plain = type(
        "Plain",
        (),
        {
            "__table__": Table(
                "demo_plain",
                md,
                Column("id", Integer, primary_key=True),
                Column("tenant_id", String(5)),
            )
        },
    )
    pkg = types.ModuleType("sm024pkg")
    models = types.ModuleType("sm024pkg.models")
    models.Scoped, models.Plain = scoped, plain
    monkeypatch.setitem(sys.modules, "sm024pkg", pkg)
    monkeypatch.setitem(sys.modules, "sm024pkg.models", models)

    mod_cls = type("DemoModule", (), {"__module__": "sm024pkg.module"})
    assert [t.name for t in module_tables(mod_cls())] == ["demo_scoped"]


# ── SM025: multi_tenant on, but nothing resolves the tenant ─────────────


def test_multi_tenant_without_resolver_warns():
    from simple_module_core.diagnostics import DiagnosticLevel, check_tenant_resolver

    diags = check_tenant_resolver(multi_tenant=True, resolver=None)
    assert [d.code for d in diags] == ["SM025"]
    assert diags[0].level == DiagnosticLevel.WARNING
    assert "tenant_resolver" in diags[0].message


def test_resolver_registered_or_tenancy_off_is_fine():
    from simple_module_core.diagnostics import check_tenant_resolver

    async def resolver(request):  # pragma: no cover - never called
        return None

    assert check_tenant_resolver(multi_tenant=True, resolver=resolver) == []
    assert check_tenant_resolver(multi_tenant=False, resolver=None) == []
