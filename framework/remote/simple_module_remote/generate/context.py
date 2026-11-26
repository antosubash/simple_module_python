"""The runtime context handed to :func:`run_operation`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from simple_module_remote.config.environments import Environment
from simple_module_remote.http.client import ApiClient

__all__ = ["RunContext"]


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
