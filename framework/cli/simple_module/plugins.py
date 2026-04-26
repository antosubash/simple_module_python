"""Plugin discovery via ``simple_module.cli_plugins`` entry points.

Real implementation lands in Task 6. For now this is a no-op so the
root Typer app imports cleanly.
"""

from __future__ import annotations

import typer


def discover_and_mount(app: typer.Typer) -> None:
    """No-op stub. Implemented in Task 6."""
