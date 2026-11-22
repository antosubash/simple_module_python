"""Default installation channel and the temporary rolling-upgrade bridge."""

from simple_module_core.runtime.deprecation import deprecate

from background_tasks.core.constants import DEFAULT_INVALIDATION_CHANNEL

LEGACY_CHANNEL_BRIDGE = deprecate(
    "global Redis invalidation channel bridge",
    remove_in="0.1.0",
    use="the database-derived installation channel",
)


def installation_channel(installation_id: str | None) -> str | None:
    """No identity before migrations means local invalidation only."""
    if installation_id is None:
        return None
    return f"{DEFAULT_INVALIDATION_CHANNEL}.{installation_id}"
