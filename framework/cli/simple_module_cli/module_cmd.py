"""``smpy module`` — commands for developing a module out-of-tree (own repo)."""

from __future__ import annotations

import typer

module_app = typer.Typer(help="Develop a SimpleModule module outside a host repo.")
