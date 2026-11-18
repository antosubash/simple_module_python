"""Run the API and Vite together; every child has an owned process group."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli._migration_support import resolve_project_root
from simple_module_cli.gen_cmd import client_app_dir, run_generation


def check_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def choose_vite_port(requested: int | None, *, api_port: int) -> int:
    if requested == api_port:
        raise ValueError("Vite and API ports must differ")
    if requested is not None:
        try:
            check_port(requested)
        except OSError as exc:
            raise ValueError(f"Vite port {requested} is unavailable: {exc}") from exc
        return requested
    for port in range(5050, 65536):
        if port == api_port:
            continue
        try:
            check_port(port)
        except OSError:
            continue
        return port
    raise ValueError("No free Vite port found")


def stop_children(children: list[subprocess.Popen]) -> None:
    for child in children:
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    for child in children:
        with suppress(subprocess.TimeoutExpired):
            child.wait(timeout=max(0, deadline - time.monotonic()))
    for child in children:
        # A reloader or npm may exit before its descendants. Kill the group even
        # when the leader was reaped; never look up or kill processes by port/name.
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)


class _StopDev(BaseException):
    def __init__(self, signum: int):
        self.signum = signum


def run_dev(root: Path, *, port: int = 8000, vite_port: int | None = None) -> int:
    from simple_module_core.dotenv import load_dotenv_into_environ

    root = root.resolve()
    client = client_app_dir(root)
    load_dotenv_into_environ(root / ".env")
    run_generation(root)
    check_port(port)
    selected = choose_vite_port(vite_port, api_port=port)
    env = {
        **os.environ,
        "SM_PROJECT_ROOT": str(root),
        "SM_VITE_DEV_URL": f"http://localhost:{selected}",
    }
    npm = shutil.which("npm")
    if npm is None:
        raise ValueError("npm not found on PATH; install Node.js first")
    workspace = client == root / "host/client_app"
    entry = "host.main:app" if workspace else "main:app"
    api = [
        sys.executable,
        "-m",
        "uvicorn",
        entry,
        "--reload",
        "--port",
        str(port),
        "--reload-dir",
        str(root),
        "--reload-include",
        "*locales/*.json",
    ]
    vite = [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(selected), "--strictPort"]
    typer.echo(f"API: http://localhost:{port}   Vite: {env['SM_VITE_DEV_URL']}")
    children: list[subprocess.Popen] = []
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def stop(signum, _frame):
        raise _StopDev(signum)

    try:
        for sig in previous:
            signal.signal(sig, stop)
        children.append(subprocess.Popen(api, cwd=root, env=env, start_new_session=True))
        children.append(subprocess.Popen(vite, cwd=client, env=env, start_new_session=True))
        while True:
            for child in children:
                code = child.poll()
                if code is not None:
                    return code if code >= 0 else 128 - code
            time.sleep(0.1)
    except _StopDev as exc:
        return 128 + exc.signum
    finally:
        # A second Ctrl-C must not interrupt cleanup and leave the other group alive.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        try:
            stop_children(children)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def dev_command(
    port: Annotated[int, typer.Option(min=1, max=65535, help="API port.")] = 8000,
    vite_port: Annotated[
        int | None,
        typer.Option(min=1, max=65535, help="Vite port (default: first free from 5050)."),
    ] = None,
) -> None:
    """Generate frontend files, then supervise the API and Vite until either exits."""
    try:
        code = run_dev(resolve_project_root(), port=port, vite_port=vite_port)
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    raise typer.Exit(code)
