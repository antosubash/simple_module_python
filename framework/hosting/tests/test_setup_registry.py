"""SetupRegistry: which steps gate the app, and how a raising step counts.

The Keycloak case is the important one. Counting superusers in the host
would be the obvious implementation and would lock every Keycloak install
out of its own application permanently, because those installs have an
empty local users table by design. The gate is a registry so a module can
decline to contribute.

The middleware that consumes this lives in ``test_setup_gate``.
"""

from __future__ import annotations

from simple_module_core.setup_steps import SetupRegistry, SetupStep


def _step(step_id: str, done: bool, *, required: bool = True, order: int = 100) -> SetupStep:
    async def is_complete(_app) -> bool:
        return done

    return SetupStep(
        id=step_id, title=step_id, is_complete=is_complete, required=required, order=order
    )


def _raising_step(step_id: str) -> SetupStep:
    async def is_complete(_app):
        raise RuntimeError("database went away")

    return SetupStep(id=step_id, title=step_id, is_complete=is_complete)


async def test_empty_registry_is_complete() -> None:
    """No module contributed a step — nothing can gate the app.

    This is the Keycloak path: identity lives elsewhere, so no step exists.
    """
    registry = SetupRegistry()

    assert not registry
    assert await registry.is_setup_complete(None)


async def test_incomplete_step_blocks() -> None:
    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=False))

    assert not await registry.is_setup_complete(None)


async def test_complete_step_releases() -> None:
    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=True))

    assert await registry.is_setup_complete(None)


async def test_optional_step_never_blocks() -> None:
    registry = SetupRegistry()
    registry.add(_step("host.site_name", done=False, required=False))

    assert await registry.is_setup_complete(None)


async def test_raising_step_counts_as_complete() -> None:
    """A transient DB error must not open an anonymous admin-creation form.

    Failing closed here would be failing open on security: the wizard lets an
    unauthenticated visitor create an administrator.
    """
    registry = SetupRegistry()
    registry.add(_raising_step("users.administrator"))

    assert await registry.is_setup_complete(None)


async def test_incomplete_lists_only_pending_required_steps() -> None:
    registry = SetupRegistry()
    registry.add(_step("a", done=True))
    registry.add(_step("b", done=False))
    registry.add(_step("c", done=False, required=False))

    pending = await registry.incomplete(None)

    assert [s.id for s in pending] == ["b"]


def test_steps_sort_by_order() -> None:
    registry = SetupRegistry()
    registry.add(_step("late", done=True, order=90))
    registry.add(_step("early", done=True, order=10))

    assert [s.id for s in registry.all_steps] == ["early", "late"]


def test_owner_is_stamped() -> None:
    registry = SetupRegistry()
    registry.set_owner("users")
    registry.add(_step("users.administrator", done=True))
    registry.set_owner("")

    assert registry.all_steps[0].module == "users"
