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
    assert reg.source_labels("records") == {"records.faq.edit": "Edit FAQ"}
    assert reg.source_labels("users") == {}


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


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_failed_source_recovers_after_the_retry_window() -> None:
    calls = {"n": 0}

    def flaky() -> list[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db not ready")
        return ["flaky.read"]

    clock = _Clock()
    reg = PermissionRegistry(clock=clock)
    reg.add_source("flaky", flaky)
    assert reg.all_permissions == []
    assert not reg.has("flaky.read")  # inside the window: not called again
    assert calls["n"] == 1
    clock.now += PermissionRegistry.SOURCE_RETRY_SECONDS
    assert reg.has("flaky.read")  # no invalidate_source needed
    assert "flaky.read" in reg.all_permissions
    assert calls["n"] == 2


def test_permanent_failure_logs_once_per_window(caplog) -> None:
    calls = {"n": 0}

    def broken() -> list[str]:
        calls["n"] += 1
        raise RuntimeError("misconfigured")

    clock = _Clock()
    reg = PermissionRegistry(clock=clock)
    reg.add_source("broken", broken)
    with caplog.at_level(logging.ERROR):
        for _ in range(50):
            assert reg.all_permissions == []
        assert (calls["n"], len(caplog.records)) == (1, 1)
        assert caplog.records[0].exc_info is not None
        clock.now += PermissionRegistry.SOURCE_RETRY_SECONDS + 1
        for _ in range(50):
            assert reg.all_permissions == []
    assert (calls["n"], len(caplog.records)) == (2, 2)


def test_invalidate_source_retries_a_failed_source_at_once() -> None:
    state = {"ok": False}

    def source() -> list[str]:
        if not state["ok"]:
            raise RuntimeError("not yet")
        return ["late.read"]

    reg = PermissionRegistry(clock=_Clock())
    reg.add_source("late", source)
    assert reg.all_permissions == []
    state["ok"] = True
    reg.invalidate_source("late")
    assert reg.all_permissions == ["late.read"]
