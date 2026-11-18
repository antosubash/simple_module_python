"""Build the production image and check health plus a rendered frontend asset."""

from __future__ import annotations

import re
import signal
import subprocess
import sys
import time
from html import unescape
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4


def first_asset(html: str) -> str:
    match = re.search(
        r"""(?:src|href)\s*=\s*["'](/static/dist/[^"'?#<>\s]+\.(?:js|css)(?:\?[^"']*)?)["']""",
        html,
    )
    if not match:
        raise RuntimeError("Rendered page has no /static/dist/*.js or .css asset")
    return unescape(match[1])


def get(url: str) -> str:
    # urlopen follows the anonymous root page's redirects (login or setup).
    with urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned {response.status}, expected 200")
        return response.read().decode("utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["docker", "build", "-t", "sm-ci-smoke", "."], cwd=root, check=True)
    container = f"sm-ci-smoke-{uuid4().hex}"
    passed = False
    try:
        # The entrypoint generates secrets, seeds the admin and migrates SQLite.
        # Let Docker allocate the loopback port to avoid a free-port race.
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container,
                "-p",
                "127.0.0.1::8000",
                "-e",
                "SM_ENVIRONMENT=production",
                "-e",
                "SM_DATABASE_URL=sqlite+aiosqlite:////app/data/app.db",
                "sm-ci-smoke",
            ],
            check=True,
        )
        address = subprocess.run(
            ["docker", "port", container, "8000/tcp"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        base = f"http://{address}"
        deadline = time.monotonic() + 120
        while True:
            try:
                get(f"{base}/health")
                break
            except (OSError, RuntimeError) as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError("/health did not return 200 within 120 seconds") from exc
                time.sleep(1)
        asset = first_asset(get(f"{base}/"))
        get(f"{base}{asset}")
        passed = True
        print(f"Docker smoke passed: /health and {asset} returned 200")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Docker smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if not passed:
                subprocess.run(["docker", "logs", container], check=False)
        finally:
            subprocess.run(["docker", "rm", "-f", container], check=False)


def terminate(signum: int, _frame: object) -> None:
    # GitHub cancellation sends SIGTERM; unwind the cleanup block too.
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    sys.exit(main())
