"""All pytest entry points must use pytest-asyncio for async fixtures."""

import shlex
import tomllib
from pathlib import Path


def test_anyio_plugin_is_disabled_and_compatibility_marker_is_registered():
    root = Path(__file__).resolve().parents[2]
    options = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    args = shlex.split(options["addopts"])
    assert any(args[i : i + 2] == ["-p", "no:anyio"] for i in range(len(args)))
    assert (
        "anyio: compatibility marker (tests run on pytest-asyncio; "
        "anyio plugin disabled via -p no:anyio)"
    ) in options["markers"]
