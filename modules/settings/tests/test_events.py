from __future__ import annotations

import pytest
from simple_module_core.events import EventBus

from settings.contracts.events import SettingsReloaded


@pytest.mark.asyncio
async def test_publish_and_subscribe() -> None:
    bus = EventBus()
    received: list[SettingsReloaded] = []

    async def handler(evt: SettingsReloaded) -> None:
        received.append(evt)

    bus.subscribe(SettingsReloaded, handler)
    await bus.publish(SettingsReloaded(package="users", changed=("allow_signup",)))
    assert received == [SettingsReloaded(package="users", changed=("allow_signup",))]
