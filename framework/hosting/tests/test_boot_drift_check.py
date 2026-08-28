"""A drifted schema must fail the boot unless the install is genuinely new.

Two situations both leave ``host.migrations`` outstanding, and they need
opposite handling:

- a fresh deployment, where the wizard should run the migrations;
- a configured install whose schema fell behind, where serving traffic is the
  failure ``SM010`` exists to prevent — and where ``/setup``'s unauthenticated
  migration endpoint would become reachable on a live system.

Gating the boot check on "is setup complete" cannot tell them apart, because
the behind-head schema is itself one of the incomplete steps. This pins the
distinction ``_is_first_run`` draws instead.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from simple_module_core.setup_steps import SetupRegistry, SetupStep
from simple_module_hosting._lifespan import _is_first_run
from simple_module_hosting.setup_gate import STEP_MIGRATIONS

pytestmark = pytest.mark.anyio


def _step(step_id: str, done: bool) -> SetupStep:
    async def is_complete(_app) -> bool:
        return done

    return SetupStep(id=step_id, title=step_id, is_complete=is_complete)


def _app(registry) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(setup_registry=registry)))


async def test_fresh_install_is_first_run() -> None:
    """Nothing configured: the wizard should get a chance to migrate."""
    registry = SetupRegistry()
    registry.add(_step(STEP_MIGRATIONS, done=False))
    registry.add(_step("users.administrator", done=False))

    assert await _is_first_run(_app(registry)) is True


async def test_configured_install_with_drift_is_not_first_run() -> None:
    """Administrators exist and only the schema is behind — fail the boot.

    This is the case the old "is setup complete" gate got wrong: the schema
    being behind made setup incomplete, so the check could never fire.
    """
    registry = SetupRegistry()
    registry.add(_step(STEP_MIGRATIONS, done=False))
    registry.add(_step("users.administrator", done=True))

    assert await _is_first_run(_app(registry)) is False


async def test_no_registry_is_not_first_run() -> None:
    """An app assembled outside create_app has no steps to reason about, so
    the older, louder behaviour is the safer default."""
    app = SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace()))

    assert await _is_first_run(app) is False


async def test_migration_step_alone_never_makes_it_first_run() -> None:
    """Guards the subtraction: host.migrations is registered on every install,
    so counting it would make every drifted install look brand new."""
    registry = SetupRegistry()
    registry.add(_step(STEP_MIGRATIONS, done=False))

    assert await _is_first_run(_app(registry)) is False
