"""Proves module-shipped CSS survives a real Tailwind build.

Every unit test around `render_modules_css` can stay green while Tailwind
emits nothing at all — the generated `@import` only pays off if Vite resolves
the `#module/<pkg>` alias and Tailwind keeps the rule. This is the one
assertion that exercises that whole chain, so it drives a genuine build
rather than inspecting the generated text.

Skipped where a build is impossible: CI's `python-tests` job installs Python
deps only (`make install-py`), so `node_modules` is absent there. The JS jobs
and local runs do have it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = [
    pytest.mark.skipif(
        not (REPO_ROOT / "node_modules").is_dir(),
        reason="node_modules absent — run `npm install` to exercise the real build",
    ),
    pytest.mark.skipif(shutil.which("npm") is None, reason="npm not on PATH"),
]


class TestModuleCssReachesBundle:
    def test_module_class_is_emitted_by_vite_build(self):
        """A class defined only in a module's styles.css appears in the built CSS.

        `.dashboard-stat-grid` is declared in modules/dashboard/dashboard/styles.css
        and referenced by no TSX anywhere, so it can only reach the bundle via the
        generated `@import "#module/dashboard/styles.css"`.
        """
        subprocess.run(
            [
                "uv",
                "run",
                "--project",
                "host",
                "smpy",
                "host",
                "gen-pages",
                "--host-dir=host/client_app",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )

        generated = (REPO_ROOT / "host/client_app/modules.generated.css").read_text(
            encoding="utf-8"
        )
        assert '@import "#module/dashboard/styles.css" layer(components);' in generated, (
            f"gen-pages did not emit the dashboard stylesheet import:\n{generated}"
        )

        subprocess.run(["npm", "run", "build"], cwd=REPO_ROOT, check=True, capture_output=True)

        built = list((REPO_ROOT / "host/static/dist/assets").glob("*.css"))
        assert built, "no CSS emitted by the build"
        combined = "\n".join(p.read_text(encoding="utf-8") for p in built)
        assert "dashboard-stat-grid" in combined, (
            "module-shipped CSS did not reach the bundle — the #module alias "
            "most likely failed to resolve"
        )
