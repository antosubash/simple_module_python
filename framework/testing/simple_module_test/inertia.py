"""Client defaults that track the app's configured Inertia asset version."""

from typing import Any

from simple_module_inertia.config import resolved_version


def inertia_headers(app: Any) -> dict[str, str]:
    """Current version header, or no defaults when the app has no Inertia."""
    config = getattr(getattr(app.state, "sm", None), "inertia_config", None)
    if config is None:
        return {}
    return {"X-Inertia-Version": resolved_version(config)}
