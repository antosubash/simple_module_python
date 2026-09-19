"""The boot-time wiring around ``InvalidationBus``.

Three regressions that no other test would catch, each cheap and each guarding a
failure that looks like something else:

* ``Services.invalidation`` is a defaulted field, so a mutable default would give
  every app one shared bus — subscribers leaking between tests, read as flake.
* ``SM007`` reports a module that overrides no hooks. ``register_invalidations``
  had to be added to that list, and a module whose only hook is this one would
  otherwise be told it does nothing.
* ``on_shutdown`` has to both stop the listener and detach it from the bus.
  Stopping without detaching leaves a bus holding a dead transport, and every
  later publish logs an exception instead of degrading quietly.
"""

from __future__ import annotations

import asyncio

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.diagnostics import DiagnosticLevel, run_diagnostics
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.services import Services

_SM007 = "SM007"


class TestServicesDefault:
    def test_each_services_gets_its_own_bus(self):
        """A shared default would leak one app's subscribers into the next."""
        first = _services()
        second = _services()

        assert first.invalidation is not second.invalidation

    def test_the_default_bus_works_rather_than_being_a_placeholder(self):
        """An app assembled outside ``create_app`` still gets a usable bus."""
        bus = _services().invalidation
        assert isinstance(bus, InvalidationBus)
        assert bus.has_transport is False
        assert bus.channels == ()


def _services() -> Services:
    """A ``Services`` with everything but ``invalidation`` left to its default."""
    return Services(
        settings=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
        menu_registry=None,  # type: ignore[arg-type]
        permissions=None,  # type: ignore[arg-type]
        feature_flags=None,  # type: ignore[arg-type]
        health_registry=None,  # type: ignore[arg-type]
        public_routes=None,  # type: ignore[arg-type]
        setup_registry=None,  # type: ignore[arg-type]
        design_packs=None,  # type: ignore[arg-type]
        audit_links=None,  # type: ignore[arg-type]
        i18n_registry=None,  # type: ignore[arg-type]
        inertia_config=None,  # type: ignore[arg-type]
        modules=(),
    )


class OnlyInvalidations(ModuleBase):
    """A module whose single contribution is a cache subscription."""

    meta = ModuleMeta(name="OnlyInvalidations")

    def register_invalidations(self, bus, app) -> None:
        bus.subscribe("only.cache", lambda inv: None)


class ContributesNothing(ModuleBase):
    meta = ModuleMeta(name="ContributesNothing")


class TestSm007:
    def test_a_module_that_only_subscribes_invalidations_is_not_flagged(self):
        """Adding the hook to ``ModuleBase`` without adding it to SM007's list
        would tell a legitimate module it overrides nothing."""
        codes = _diagnostic_codes(OnlyInvalidations())

        assert _SM007 not in codes, "register_invalidations is missing from SM007's hook list"

    def test_a_module_that_really_overrides_nothing_is_still_flagged(self):
        """The control: the check must not have been defanged."""
        assert _SM007 in _diagnostic_codes(ContributesNothing())


def _diagnostic_codes(module: ModuleBase) -> set[str]:
    return {
        d.code
        for d in run_diagnostics([module])
        if d.level in (DiagnosticLevel.INFO, DiagnosticLevel.WARNING, DiagnosticLevel.ERROR)
    }


class _StubSm:
    def __init__(self, bus: InvalidationBus) -> None:
        self.invalidation = bus


class _StubState:
    pass


class _StubApp:
    def __init__(self, bus: InvalidationBus, settings) -> None:
        from background_tasks.services import BackgroundTasksServices

        self.state = _StubState()
        self.state.sm = _StubSm(bus)
        self.state.background_tasks = BackgroundTasksServices(settings=settings)


class TestShutdown:
    async def test_shutdown_detaches_and_stops_the_transport(self, monkeypatch):
        from background_tasks.module import BackgroundTasksModule
        from background_tasks.settings import BackgroundTasksSettings

        stopped: list[bool] = []

        class _FakeTransport:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def start(self) -> None:
                pass

            async def publish(self, message: str) -> None:
                pass

            async def stop(self) -> None:
                stopped.append(True)

        import background_tasks.invalidation as bg_invalidation

        monkeypatch.setattr(bg_invalidation, "RedisInvalidationTransport", _FakeTransport)

        bus = InvalidationBus()
        app = _StubApp(bus, BackgroundTasksSettings(broadcast_invalidations=True))
        module = BackgroundTasksModule()
        await module._start_invalidation_transport(app)
        assert bus.has_transport is True

        await module.on_shutdown(app)

        assert stopped == [True], "the listener was never stopped"
        assert bus.has_transport is False, "the bus still holds a dead transport"
        assert app.state.background_tasks.invalidation_transport is None


class TestStartupAgainstADeadBroker:
    """``on_startup`` must complete even when Redis is unreachable.

    The hook is a level above ``RedisInvalidationTransport.start()``, which the
    degraded tests cover, and it is the level that decides whether a web worker
    boots at all. It also logs "invalidation transport on …" unconditionally,
    which is what made the wedged-listener defect (F7) invisible — so the boot
    path deserves its own test rather than inheriting the transport's.
    """

    async def test_an_unreachable_url_does_not_fail_the_boot(self):
        import socket

        from background_tasks.module import BackgroundTasksModule
        from background_tasks.settings import BackgroundTasksSettings

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = int(probe.getsockname()[1])

        bus = InvalidationBus()
        app = _StubApp(
            bus,
            BackgroundTasksSettings(
                broadcast_invalidations=True,
                broker_url=f"redis://127.0.0.1:{dead_port}/0",
            ),
        )
        module = BackgroundTasksModule()

        # The property under test is simply "returns": an accelerator over a TTL
        # must never stop a worker that can otherwise serve every request.
        await asyncio.wait_for(module._start_invalidation_transport(app), timeout=30)
        try:
            assert bus.has_transport is True, "the transport should be installed optimistically"
        finally:
            await module.on_shutdown(app)

    async def test_publishing_through_a_dead_broker_still_evicts_locally(self):
        """And the app keeps working afterwards, degraded to per-process."""
        import socket

        from background_tasks.module import BackgroundTasksModule
        from background_tasks.settings import BackgroundTasksSettings

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = int(probe.getsockname()[1])

        bus = InvalidationBus()
        seen: list[object] = []
        bus.subscribe("c", seen.append)
        app = _StubApp(
            bus,
            BackgroundTasksSettings(
                broadcast_invalidations=True,
                broker_url=f"redis://127.0.0.1:{dead_port}/0",
            ),
        )
        module = BackgroundTasksModule()
        await module._start_invalidation_transport(app)
        try:
            await asyncio.wait_for(bus.publish("c", key="k"), timeout=30)
        finally:
            await module.on_shutdown(app)

        assert len(seen) == 1


class TestSettingsValidation:
    def test_an_empty_channel_name_is_rejected(self):
        """Subscribing to "" would silently hear nothing."""
        from background_tasks.settings import BackgroundTasksSettings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BackgroundTasksSettings(invalidation_channel="")

    async def test_both_new_fields_reach_the_settings_admin_surface(self, app):
        """An operator who cannot see a field cannot configure it.

        Asserted through ``collect_module_settings`` — what the settings screens
        and ``import-from-env`` actually read — rather than through
        ``model_fields``, which would only restate the dataclass back to itself.
        """
        from settings._module_settings import collect_module_settings

        views = collect_module_settings(app)
        background = next((v for v in views if v.package == "background_tasks"), None)
        assert background is not None, "background_tasks is absent from the settings surface"

        fields = {f.name: f for f in background.fields}
        assert {"broadcast_invalidations", "invalidation_channel"} <= set(fields)
        # Both are env-readable, unlike the users ones — the admin panel says so,
        # and that label is the only place an operator learns which knob works.
        assert fields["broadcast_invalidations"].env_var == "SM_BG_TASKS_BROADCAST_INVALIDATIONS"
        assert fields["invalidation_channel"].env_var == "SM_BG_TASKS_INVALIDATION_CHANNEL"
