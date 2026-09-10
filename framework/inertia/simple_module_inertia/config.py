"""Adapter configuration.

Field names match upstream ``fastapi-inertia`` so ``simple_module_hosting``'s
``setup_inertia`` keeps constructing it the same way. The one addition is that
``version`` may be a zero-arg callable, so an app can derive the asset version
from its Vite manifest hash at boot instead of hard-coding ``"1.0"``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.templating import Jinja2Templates


@dataclass
class InertiaConfig:
    templates: Jinja2Templates
    environment: Literal["development", "production"] = "development"
    version: str | Callable[[], str] = "1.0"
    dev_url: str = "http://localhost:5173"
    ssr_url: str = "http://localhost:13714"
    ssr_enabled: bool = False
    manifest_json_path: str = ""
    root_directory: str = "src"
    root_template_filename: str = "index.html"
    entrypoint_filename: str = "main.js"
    use_flash_messages: bool = False
    use_flash_errors: bool = False
    flash_message_key: str = "messages"
    flash_error_key: str = "errors"
    assets_prefix: str = ""
    extra_template_context: dict[str, Any] = field(default_factory=dict)


def resolved_version(config: InertiaConfig) -> str:
    """The asset version as a string, calling ``version`` if it is a callable."""
    version = config.version
    return str(version()) if callable(version) else str(version)
