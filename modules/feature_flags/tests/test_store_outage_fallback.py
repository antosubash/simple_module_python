"""Boot tolerates a feature-flag store outage by falling back to defaults.

If the DB read fails during ``on_startup`` (table missing, store unreachable),
the app must still boot — feature flags are explicitly defaulted at
``register_feature_flags`` time, and an outage that flips every flag to
"unknown" would cascade into every dependent module. The fallback is logged
so an operator can react.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from feature_flags.module import FeatureFlagsModule
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry


class _BoomService:
    """Stand-in service whose ``hydrate_registry`` always blows up."""

    async def hydrate_registry(self, registry):
        raise RuntimeError("simulated store outage")


@pytest.mark.anyio
async def test_on_startup_swallows_store_failure_and_keeps_registry_defaults(monkeypatch, caplog):
    """A DB failure during hydrate must not stop the app from booting."""

    registry = FeatureFlagRegistry()
    registry.add(
        FeatureFlagDefinition(
            name="my_flag",
            description="anything",
            default_enabled=True,
        )
    )

    class _SessionCM:
        async def __aenter__(self):
            return MagicMock(name="session")

        async def __aexit__(self, *args):
            return None

    fake_app = MagicMock()
    fake_app.state.sm = SimpleNamespace(
        feature_flags=registry,
        db=SimpleNamespace(session_factory=lambda: _SessionCM()),
    )

    # ``on_startup`` does ``from feature_flags.service import FeatureFlagService``
    # *inside* the method body — patching ``feature_flags.module.FeatureFlagService``
    # would be a no-op since the name is never bound there. Patch the source
    # module so the deferred import resolves to ``_BoomService``.
    import feature_flags.module as ff_module
    import feature_flags.service as ff_service

    monkeypatch.setattr(ff_service, "FeatureFlagService", lambda *a, **kw: _BoomService())

    module = FeatureFlagsModule()
    with caplog.at_level(logging.WARNING, logger=ff_module.__name__):
        await module.on_startup(fake_app)

    # 1. Booted cleanly (no exception escaped).
    # 2. Registry retains its default value — the boot path didn't try to
    #    "blank out" the flag in lieu of unknown DB state.
    assert registry.is_enabled("my_flag") is True
    # 3. Operators see a warning so they can investigate the outage.
    assert any("hydrate_failed" in r.message for r in caplog.records), (
        f"Expected hydrate_failed warning, got: {[r.message for r in caplog.records]!r}"
    )
