"""The runtime context handed to :func:`run_operation`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from simple_module_remote.config.environments import Environment
from simple_module_remote.http.client import ApiClient

__all__ = ["RunContext"]


def _keep(text: str) -> str:
    return text


@dataclass
class RunContext:
    env: Environment
    client_factory: Callable[[], ApiClient]
    is_tty: bool
    stdout: TextIO
    stderr: TextIO
    stdin: TextIO
    prompt: Callable[[str], str]
    root: dict
    # stdin and stderr are both terminals: a confirmation prompt can be answered.
    interactive: bool = False
    login_hint: str = ""
    # Said after a 404/422: the command may come from a schema older than the server's.
    schema_hint: str = ""
    tenant: str | None = None
    # The operation is known to refuse tokens (a session-only route reached through `api`).
    session_only: bool = False
    # Strips the active token from server-derived text before it is shown (set per request).
    redact: Callable[[str], str] = _keep
