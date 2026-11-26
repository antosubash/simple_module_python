"""The scaffold's form actions name the ``/api`` routes that do the same.

Every non-GET view route must declare ``api_equivalent`` (or an exemption); a
scaffolded module mounted on an app must pass the same walker the host test
runs (``simple_module_hosting.auth.api_equivalent.view_route_offenders``).
"""

from __future__ import annotations

import os
import subprocess
import sys

from simple_module_cli.scaffold.scaffolding import create_module

_PROBE = "\n".join(
    [
        "from fastapi import FastAPI",
        "from fastapi.routing import iter_route_contexts",
        "from equiv_probe.module import EquivProbeModule",
        "from simple_module_hosting.auth.api_equivalent import view_route_offenders",
        "from simple_module_hosting.boot._module_routes import wire_module_routes",
        "app = FastAPI()",
        "wire_module_routes(app, EquivProbeModule())",
        "mutating = [c.path for c in iter_route_contexts(app.routes)",
        "            if not c.path.startswith('/api/') and set(c.methods or ()) - {'GET', 'HEAD'}]",
        "assert len(mutating) == 2, mutating",
        "offenders = view_route_offenders(app)",
        "assert not offenders, offenders",
    ]
)


def test_scaffolded_view_posts_declare_api_equivalents(tmp_path):
    dest = create_module(tmp_path / "module", "equiv_probe")
    check = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env={**os.environ, "PYTHONPATH": str(dest)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert check.returncode == 0, check.stdout + check.stderr
