"""Runtime permission sources on PermissionRegistry (GH #334)."""

from __future__ import annotations

import logging

from simple_module_core.permissions import PermissionRegistry


def test_source_permissions_in_all_permissions_and_groups() -> None:
    reg = PermissionRegistry()
    reg.add_group("users", ["users.view"])
    reg.add_source("records", lambda: ["records.product.edit", ("records.faq.edit", "Edit FAQ")])

    assert "records.product.edit" in reg.all_permissions
    assert reg.has("records.faq.edit")
    group = next(g for g in reg.groups if g.name == "records")
    assert sorted(group.permissions) == ["records.faq.edit", "records.product.edit"]
    assert reg.source_labels() == {"records.faq.edit": "Edit FAQ"}


def test_invalidate_source_refreshes() -> None:
    reg = PermissionRegistry()
    types = ["a"]
    reg.add_source("records", lambda: [f"records.{t}.edit" for t in types])
    assert reg.all_permissions == ["records.a.edit"]

    types.append("b")
    assert reg.all_permissions == ["records.a.edit"]  # cached
    reg.invalidate_source("records")
    assert reg.all_permissions == ["records.a.edit", "records.b.edit"]


def test_failing_source_is_isolated(caplog) -> None:
    reg = PermissionRegistry()
    reg.add_group("users", ["users.view"])

    def boom() -> list[str]:
        raise RuntimeError("nope")

    reg.add_source("bad", boom)
    reg.add_source("good", lambda: ["good.x"])
    with caplog.at_level(logging.ERROR):
        assert reg.all_permissions == ["good.x", "users.view"]
    assert any("bad" in r.getMessage() for r in caplog.records)


def test_admin_implicit_all_includes_sources() -> None:
    reg = PermissionRegistry()
    reg.add_source("records", lambda: ["records.product.edit"])
    assert "records.product.edit" in reg.get_permissions_for_roles(["admin"])
