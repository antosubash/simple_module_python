"""Fail when a built wheel ships a JS test file (GH #900).

A host's Vite dep scan walks every installed module's package directory, so a
``*.test.ts`` inside a wheel makes it import ``vitest``, which an app does not
install: "Failed to run dependency scan". JS tests belong in ``tests-js/``.

Usage: ``python scripts/check_wheel_contents.py <dist-dir>`` (run by
``make ci-build-packages`` on the wheels it builds). Exit 0 if clean, 1 otherwise.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from pathlib import Path

# The module template's `[tool.hatch.build.targets.wheel] exclude` list.
FORBIDDEN = ("*.test.*", "*.spec.*", "test-dom.tsx", "*/page-tests/*")


def forbidden_members(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    return [
        name
        for name in names
        if any(
            fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(Path(name).name, pattern)
            for pattern in FORBIDDEN
        )
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="directory holding the built wheels")
    args = parser.parse_args(argv)

    wheels = sorted(args.dist.glob("*.whl"))
    if not wheels:
        print(f"no wheels found in {args.dist}", file=sys.stderr)
        return 1
    errors = [f"{w.name}: {m}" for w in wheels for m in forbidden_members(w)]
    for error in errors:
        print(f"ERROR: JS test file in a published wheel: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK: {len(wheels)} wheels carry no JS test files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
