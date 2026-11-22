"""Keep build tools out of runtime images and share worker/beat wiring safely."""

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def runtime_instructions(path):
    source = (ROOT / path).read_text()
    stages = re.split(r"(?im)^FROM ", source)
    assert len(stages) == 3, "Expected separate builder and runtime stages"
    assert stages[1].splitlines()[0].endswith(" AS builder")
    assert "uv sync --all-packages" in stages[1]
    runtime = stages[2]
    assert runtime.splitlines()[0] == "python:3.12-slim-bookworm AS runtime"
    return "\n".join(
        line for line in runtime.replace("\\\n", " ").splitlines() if not line.startswith("#")
    )


@pytest.mark.parametrize(
    ("path", "user", "artifacts"),
    [
        (
            "Dockerfile",
            "app",
            {".venv", "pyproject.toml", "docker", "framework", "modules", "host"},
        ),
        (
            "docker/worker.Dockerfile",
            "worker",
            {".venv", "pyproject.toml", "framework", "modules", "host", "scripts"},
        ),
    ],
)
def test_runtime_copies_only_runtime_artifacts(path, user, artifacts):
    runtime = runtime_instructions(path)
    copies = [shlex.split(line) for line in runtime.splitlines() if line.startswith("COPY ")]
    assert len(copies) == len(artifacts)
    assert {copy[-2] for copy in copies} == {f"/app/{name}" for name in artifacts}
    for copy in copies:
        assert "--from=builder" in copy
        assert copy[-1].rstrip("/") == copy[-2]
    assert f"chown -R {user}:{user} /app" in runtime
    assert f"USER {user}" in runtime
    assert re.search(rf"useradd .*--uid 10001 .*\b{user}\b", runtime)
    assert 'PATH="/app/.venv/bin:$PATH"' in runtime
    assert "UV_SYSTEM_PYTHON" not in runtime
    assert "build-essential" not in runtime
    assert not re.search(r"\b(?:uv|uvx|pip|npm|node)\b", runtime)
    assert "mkdir -p /app/data/uploads" in runtime
    assert "ln -s /app/data/uploads /app/uploads" in runtime


def test_worker_installs_frozen_production_dependencies_and_runs_celery_directly():
    source = (ROOT / "docker/worker.Dockerfile").read_text()
    assert "uv sync --all-packages --frozen --no-dev" in source
    runtime = runtime_instructions("docker/worker.Dockerfile")
    cmd = next(
        line.removeprefix("CMD ") for line in runtime.splitlines() if line.startswith("CMD [")
    )
    assert json.loads(cmd) == ["celery", "-A", "scripts.run_worker:celery", "worker", "-l", "info"]


def test_worker_healthcheck_distinguishes_beat_from_workers():
    runtime = runtime_instructions("docker/worker.Dockerfile")
    healthcheck = runtime.split("HEALTHCHECK", 1)[1].split("\nCMD [", 1)[0]
    assert "ENV CELERY_APP=scripts.run_worker:celery" in runtime
    assert r"tr '\0' '\n' < /proc/1/cmdline | grep -qx beat" in healthcheck
    assert "kill -0 1" in healthcheck
    assert 'celery -A "$CELERY_APP" inspect ping -d "celery@$HOSTNAME"' in healthcheck
    assert "if " in healthcheck and "else" in healthcheck and "fi" in healthcheck


@pytest.mark.parametrize(
    ("role", "ping_status"),
    [("beat", 0), ("beat", 1), ("worker", 0), ("worker", 1), ("heartbeat", 1)],
)
def test_healthcheck_shell_only_pings_workers(tmp_path, role, ping_status):
    runtime = runtime_instructions("docker/worker.Dockerfile")
    healthcheck = runtime.split("HEALTHCHECK", 1)[1].split("\nCMD [", 1)[0].split("CMD ", 1)[1]
    cmdline = tmp_path / "cmdline"
    cmdline.write_bytes(f"celery\0-A\0scripts.run_worker:celery\0{role}\0-l\0info\0".encode())
    celery = tmp_path / "celery"
    celery.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@"\nexit {ping_status}\n')
    celery.chmod(0o755)
    # Use fixture argv and a process we own rather than the host's PID 1.
    healthcheck = healthcheck.replace("/proc/1/cmdline", shlex.quote(str(cmdline))).replace(
        "kill -0 1", "kill -0 $$"
    )
    result = subprocess.run(
        ["/bin/sh", "-c", healthcheck],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CELERY_APP": "scripts.run_worker:celery",
            "HOSTNAME": "test-worker",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == (0 if role == "beat" else ping_status)
    assert result.stdout.splitlines() == (
        []
        if role == "beat"
        else ["-A", "scripts.run_worker:celery", "inspect", "ping", "-d", "celery@test-worker"]
    )


@pytest.mark.parametrize("role", ["worker", "beat"])
def test_compose_uses_one_redis_url_and_direct_celery_commands(role):
    service = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"][role]
    environment = service["environment"]
    assert environment["SM_REDIS_URL"] == "${SM_REDIS_URL:-redis://redis:6379/4}"
    assert "SM_BG_TASKS_BROKER_URL" not in environment
    assert "SM_BG_TASKS_RESULT_BACKEND" not in environment
    assert service["command"][:4] == ["celery", "-A", "scripts.run_worker:celery", role]
    assert "appdata:/app/data" in service["volumes"]
