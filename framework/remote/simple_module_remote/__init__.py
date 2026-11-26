"""Client-only engine for a per-project CLI over a simple_module app's REST API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("simple_module_remote")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
