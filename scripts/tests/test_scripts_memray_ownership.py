"""An occupied loadtest port must leave its owner untouched (#629)."""

import os
import signal
import subprocess
from contextlib import suppress
from pathlib import Path


def test_memray_refuses_occupied_port_before_running_tools(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/loadtest_memray.sh"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "uv": 'echo uv >> "$CALLS"; exit 1',
        "curl": "exit 0",
        "lsof": 'echo lsof >> "$CALLS"; echo 2147483647',
        "python3": 'echo "Address already in use" >&2; exit 1',
    }.items():
        tool = bin_dir / name
        tool.write_text(f"#!/bin/bash\n{body}\n")
        tool.chmod(0o755)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", str(script)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PORT": "8000",
            "SKIP_SEED": "1",
            "BASH_ENV": "",
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CALLS": str(calls),
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert not calls.exists(), result.stdout + result.stderr


def test_memray_cleanup_stops_owned_descendants(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/loadtest_memray.sh"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "python3": "exit 0",  # Socket binding is unavailable in some sandboxes.
        "curl": "while [ ! -f child.pid ]; do sleep 0.01; done",
        "lsof": 'echo "$UNRELATED_PID"',
        "uv": """if [ "$2 $3" = "memray run" ]; then
  echo $$ > wrapper.pid
  sleep 60 &
  echo $! > child.pid
  trap 'wait; exit 0' INT TERM
  wait
fi""",
    }.items():
        tool = bin_dir / name
        tool.write_text(f"#!/bin/sh\n{body}\n")
        tool.chmod(0o755)
    unrelated = subprocess.Popen(["sleep", "60"])
    try:
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", str(script)],
            cwd=tmp_path,
            env={
                **os.environ,
                "SKIP_SEED": "1",
                "BASH_ENV": "",
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "UNRELATED_PID": str(unrelated.pid),
            },
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert unrelated.poll() is None
        for name in ("wrapper.pid", "child.pid"):
            pid = int((tmp_path / name).read_text())
            proc = Path(f"/proc/{pid}/stat")
            assert not proc.exists() or proc.read_text().split()[2] == "Z"
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
        for name in ("child.pid", "wrapper.pid"):
            path = tmp_path / name
            if path.exists():
                with suppress(ProcessLookupError):
                    os.kill(int(path.read_text()), signal.SIGKILL)
