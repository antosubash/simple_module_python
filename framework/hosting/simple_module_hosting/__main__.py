"""Module entry point: ``python -m simple_module_hosting`` invokes the host CLI.

Without this, ``python -m simple_module_hosting.host_cli`` would import the
module without running the Typer app — silently no-op'ing commands like
``gen-pages``. Provides the same Typer ``app`` callable that the
``simple_module_cli.cli_plugins`` entry point exposes as ``smpy host``.
"""

from __future__ import annotations

from simple_module_hosting.host_cli import app

if __name__ == "__main__":
    app()
