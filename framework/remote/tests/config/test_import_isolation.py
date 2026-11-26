"""The client engine must run in an environment without the server stack."""

import subprocess
import sys

SERVER_ROOTS = {"fastapi", "sqlmodel", "sqlalchemy", "starlette"}

PROBE = f"""
import simple_module_remote, sys
roots = {SERVER_ROOTS!r}
bad = [
    m for m in sys.modules
    if m.split('.')[0] in roots
    or (m.startswith('simple_module_') and not m.startswith('simple_module_remote'))
]
print(bad)
raise SystemExit(bool(bad))
"""


def test_engine_imports_no_server_packages():
    result = subprocess.run(
        [sys.executable, "-I", "-c", PROBE], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
