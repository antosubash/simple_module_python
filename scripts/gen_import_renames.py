"""Write the ``smpy fix-imports`` rename table from the framework's layout shims.

The CLI ships without a dependency on ``simple_module_core``, so the old -> new
paths are frozen into ``import_renames.json``.
``host/tests/test_deprecation_expiry.py`` fails when the file is stale.

Usage: ``uv run python scripts/gen_import_renames.py``
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "framework/cli/simple_module_cli/updates/import_renames.json"


def main() -> None:
    sys.path.insert(0, str(ROOT / "host/tests"))
    layout_renames = importlib.import_module("test_deprecation_expiry").layout_renames

    payload = {
        "_generated_by": "scripts/gen_import_renames.py",
        "renames": layout_renames(),
    }
    TARGET.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(payload['renames'])} renames to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
