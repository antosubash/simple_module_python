"""Explicit overrides must change consumers without changing plain additions."""

from dataclasses import dataclass

import pytest
from simple_module_core.events import Event, EventBus
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.rate_limit import RateLimitRegistry, RateLimitRule
from simple_module_core.resources import ResourceType, ResourceTypeError, ResourceTypeRegistry


@pytest.mark.parametrize("kind", ["exact", "regex", "prefix", "suffix"])
def test_public_removal_matches_registration_not_request(kind):
    registry = PublicRouteRegistry()
    registry.add("/page", kind=kind, methods={"GET"})
    registry.add("/page", kind=kind, methods={"POST"})
    registry.add("/page", kind=kind, methods={"GET"})
    registry.remove("/page", kind=kind, methods={"get"})
    assert not registry.matches("GET", "/page")
    assert registry.matches("POST", "/page")
    with pytest.raises(KeyError):
        registry.remove("/page", kind=kind, methods={"GET"})
    registry.remove("/page", kind=kind)
    assert not registry.routes


def test_code_revocation_does_not_touch_db_grants_or_sources():
    registry = PermissionRegistry()
    registry.add_source("dynamic", lambda: ["orders.view"])
    registry.map_role("tenant:member", ["orders.view", "orders.edit"])
    assert "orders.edit" in registry.role_map["tenant:member"]  # warm cache
    registry.revoke_role("tenant:member", "orders.edit")
    registry.replace_role_overlays({"tenant:member": ["orders.view"]})
    assert registry.role_map["tenant:member"] == ["orders.view"]
    registry.set_role_overlay("tenant:member", ["orders.edit"])
    assert set(registry.role_map["tenant:member"]) == {"orders.view", "orders.edit"}
    registry.revoke_role("tenant:member")
    assert registry.role_map["tenant:member"] == ["orders.edit"]
    assert registry.all_permissions == ["orders.view"]
    with pytest.raises(KeyError):
        registry.revoke_role("tenant:member", "orders.edit")
    with pytest.raises(KeyError):
        registry.revoke_role("absent")


@pytest.mark.parametrize("kind", ["exact", "prefix", "regex"])
def test_rate_replacement_overrides_overlapping_methods_without_changing_siblings(kind):
    registry = RateLimitRegistry()
    add = getattr(registry, f"add_{kind}")
    add("/page", RateLimitRule("10/minute", methods={"GET", "POST"}))
    add("/page", RateLimitRule("20/minute", methods={"GET"}))
    assert registry.match("GET", "/page").rate == "10/minute"
    replacement = RateLimitRule("1/minute", methods={"get"})
    getattr(registry, f"replace_{kind}")("/page", replacement)
    add("/page", RateLimitRule("30/minute", methods={"GET"}))
    assert registry.match("GET", "/page") is replacement
    assert registry.match("POST", "/page").rate == "10/minute"
    with pytest.raises(KeyError):
        getattr(registry, f"replace_{kind}")("/absent", replacement)


def test_resource_replace_validates_before_mutating():
    registry = ResourceTypeRegistry()
    old = ResourceType("notes.note", object(), lambda key: key)
    new = ResourceType("notes.note", object(), lambda key: f"new:{key}")
    registry.register(old)
    with pytest.raises(ResourceTypeError):
        registry.register(new)
    with pytest.raises(ResourceTypeError):
        registry.replace(ResourceType("notes.note", object(), str, share_roles={"bad": ()}))
    assert registry.get("notes.note") is old
    registry.replace(new)
    assert registry.get("notes.note").select_by_id("7") == "new:7"
    with pytest.raises(KeyError):
        registry.replace(ResourceType("notes.missing", object(), str))


def test_rate_replace_preserves_unscoped_siblings_and_disabled_fallback():
    registry = RateLimitRegistry()
    registry.add_prefix("/", RateLimitRule("100/minute"))
    registry.add_exact("/page", RateLimitRule("20/minute"))
    registry.replace_exact("/page", RateLimitRule("1/minute", methods={"POST"}))
    assert registry.match("GET", "/page").rate == "20/minute"
    assert registry.match("POST", "/page").rate == "1/minute"
    registry.replace_exact(
        "/page", RateLimitRule("2/minute", methods={"POST"}), enabled=lambda: False
    )
    assert registry.match("POST", "/page").rate == "100/minute"
    assert registry.match("GET", "/page").rate == "20/minute"
    registry.replace_exact("/page", RateLimitRule("3/minute"))
    assert registry.match("GET", "/page").rate == "3/minute"
    assert registry.match("POST", "/page").rate == "3/minute"


@dataclass
class Changed(Event):
    pass


async def test_unsubscribe_and_rebind_durable_name():
    bus = EventBus()
    calls = []

    async def old(event, ctx=None):
        calls.append("old")

    async def new(event, ctx=None):
        calls.append("new")

    bus.subscribe(Changed, old)
    bus.unsubscribe(Changed, old)
    await bus.publish(Changed())
    bus.publish_nowait(Changed())
    assert calls == []
    with pytest.raises(KeyError):
        bus.unsubscribe(Changed, old)
    bus.subscribe_durable(Changed, old, name="changed")
    with pytest.raises(ValueError):
        bus.subscribe_durable(Changed, new, name="changed")
    bus.replace_durable(Changed, new, name="changed")
    with pytest.raises(TypeError):
        bus.replace_durable(Changed, None, name="changed")
    await bus.publish_durable_or_inline(Changed(), None)
    assert calls == ["new"]
    bus.unsubscribe_durable(Changed, name="changed")
    await bus.publish_durable_or_inline(Changed(), None)
    assert calls == ["new"]
    with pytest.raises(KeyError):
        bus.unsubscribe_durable(Changed, name="changed")
    with pytest.raises(KeyError):
        bus.replace_durable(Changed, old, name="missing")
