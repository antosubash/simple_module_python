"""Two real worker processes, one Redis, one database — the claim of GH #318.

Everything else about the invalidation bus is tested inside one process, where
"another worker" is a second :class:`InvalidationBus` object sharing this
process's module-level cache. That proves the plumbing and cannot prove the
point. This file boots two uvicorn processes and asks the only question that
matters: after "sign out everywhere" in worker A, does worker B stop honouring
the session?

It comes in two arms, and the control is not optional:

* **control** — ``broadcast_invalidations=false``. B must *keep* honouring the
  revoked session, because its cached counter has 300 seconds left to run. This
  reproduces the bug live, and it is what stops the treatment arm passing for
  some unrelated reason. Two earlier drafts of this test "passed" while
  measuring nothing — once because each request built a fresh HTTP client and so
  threw away the cookie that engages the cached path, once because the cache TTL
  override was spelled with a variable name nothing reads.
* **treatment** — ``broadcast_invalidations=true``. B must stop within a round
  trip, with the same 300-second TTL in force. Nothing but the broadcast can
  explain the difference.

Cost is four process boots and one Alembic run, shared across both arms. That is
paid once per session and is worth it for the only test that covers the feature's
reason to exist.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
_ADMIN = "admin@example.com"
_PASSWORD = "AdminPass1!"
_GUARDED = "/admin/users/"
_REVOKE = "/api/users/me/sessions/revoke-all"

#: Long enough that no cache expiry can be mistaken for a broadcast. The control
#: arm waits a fraction of this and must still be let in.
_CACHE_TTL_SECONDS = 300
#: How long the control arm insists the stale session keeps working, and the
#: ceiling the treatment arm must beat. Short enough to keep the suite quick,
#: long enough that a slow runner does not read as a broadcast.
_OBSERVE_SECONDS = 6.0
_BOOT_TIMEOUT_SECONDS = 120.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class _Worker:
    process: subprocess.Popen
    base_url: str

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
        if self.process.stdout is not None:
            self.process.stdout.close()


@dataclass
class _Stack:
    """A migrated database plus the environment its workers boot with."""

    db_path: str
    redis_url: str
    secret: str

    def env(self, *, broadcast: bool, channel: str) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                # "testing" rather than "development": a non-prod environment, so
                # the loopback broker passes the production guard, but without the
                # dev-only diagnostics run and manifest writes.
                "SM_ENVIRONMENT": "testing",
                "SM_DATABASE_URL": f"sqlite+aiosqlite:///{self.db_path}",
                "SM_REDIS_URL": self.redis_url,
                "SM_SECRET_KEY": self.secret,
                "SM_USERS_BOOTSTRAP_EMAIL": _ADMIN,
                "SM_USERS_BOOTSTRAP_PASSWORD": _PASSWORD,
                # BackgroundTasksSettings is env-readable (explicit env_prefix),
                # which is why the arms can differ per process without touching
                # the shared database.
                "SM_BG_TASKS_BROADCAST_INVALIDATIONS": "true" if broadcast else "false",
                "SM_BG_TASKS_INVALIDATION_CHANNEL": channel,
            }
        )
        return env


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=_ROOT, env=env, capture_output=True, text=True, timeout=600, check=False
    )


@pytest.fixture(scope="module")
def stack(redis_server, tmp_path_factory) -> _Stack:
    """Migrate a throwaway database and seed the two DB-only settings.

    ``UsersSettings`` is ``DbBackedSettings`` — it reads no environment at all —
    so ``cookie_secure`` and the cache TTL cannot be passed as env vars to the
    workers. ``smpy settings import-from-env`` is the documented path that turns
    those variables into stored overrides, so the fixture uses it, which exercises
    that path as a side effect.

    ``cookie_secure`` has to go off or the browser-equivalent client refuses to
    send the auth cookie over plain HTTP and every request 401s.
    """
    db_path = str(tmp_path_factory.mktemp("cross-process") / "qa.db")
    built = _Stack(db_path=db_path, redis_url=redis_server, secret=secrets.token_hex(32))
    env = built.env(broadcast=False, channel="unused")

    migrated = _run(
        ["uv", "run", "--project", "host", "alembic", "-c", "host/alembic.ini", "upgrade", "heads"],
        env,
    )
    assert migrated.returncode == 0, f"alembic failed:\n{migrated.stdout}\n{migrated.stderr}"

    # import-from-env writes an override for *every* SM_<PREFIX>_<FIELD> var it
    # finds, and a stored override beats the environment from then on
    # (``hydrate_settings`` passes DB values as init args, which pydantic-settings
    # ranks above its env source). Leaving the SM_BG_TASKS_* vars in this env
    # would therefore pin broadcasting to whatever this call happened to see and
    # make the per-worker env switch inert — which is exactly how the first draft
    # of this test managed to fail its own treatment arm.
    import_env = {k: v for k, v in env.items() if not k.startswith("SM_BG_TASKS_")}
    import_env["SM_USERS_COOKIE_SECURE"] = "false"
    import_env["SM_USERS_SESSION_VERSION_CACHE_TTL_SECONDS"] = str(_CACHE_TTL_SECONDS)
    imported = _run(["uv", "run", "smpy", "settings", "import-from-env"], import_env)
    assert imported.returncode == 0, f"import-from-env failed:\n{imported.stdout}{imported.stderr}"
    return built


def _boot(stack: _Stack, *, broadcast: bool, channel: str) -> _Worker:
    port = _free_port()
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "--project",
            "host",
            "uvicorn",
            "host.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=_ROOT,
        env=stack.env(broadcast=broadcast, channel=channel),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    worker = _Worker(process=process, base_url=f"http://127.0.0.1:{port}")
    deadline = time.monotonic() + _BOOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise AssertionError(f"worker died during boot:\n{output[-4000:]}")
        try:
            if httpx.get(f"{worker.base_url}/health/live", timeout=2).status_code < 500:
                return worker
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    worker.stop()
    raise AssertionError("worker did not become ready in time")


@pytest.fixture(scope="module")
def pair(stack) -> Iterator:
    """Two workers per arm, booted so the first one seeds the database alone.

    Two processes reaching a fresh database at once race on the admin/role seed
    and one of them dies with a UNIQUE violation on ``users_role.name`` — a
    pre-existing first-boot race, unrelated to invalidation, avoided here by
    letting one worker finish before the rest start.
    """
    workers: list[_Worker] = []

    def build(broadcast: bool, channel: str) -> tuple[_Worker, _Worker]:
        first = _boot(stack, broadcast=broadcast, channel=channel)
        workers.append(first)
        second = _boot(stack, broadcast=broadcast, channel=channel)
        workers.append(second)
        return first, second

    try:
        yield build
    finally:
        for worker in workers:
            worker.stop()


def _sign_in(worker: _Worker) -> httpx.Client:
    client = httpx.Client(base_url=worker.base_url, timeout=30)
    resp = client.post("/api/users/auth/login", data={"username": _ADMIN, "password": _PASSWORD})
    assert resp.status_code == 204, resp.text
    return client


def _warm(worker: _Worker, cookies: dict[str, str]) -> httpx.Client:
    """A client on *worker* whose session cookie carries a cached user context.

    One persistent client, and three requests. The revocation check only consults
    the per-process ``session_version`` cache on the *cached-context* path, and
    that path only engages once the session cookie carries the context — which
    the worker writes back on its first response. A client rebuilt per request,
    or a single warm-up, leaves every request doing a full database load, where
    the cache under test is never read and both arms would look identical.
    """
    client = httpx.Client(base_url=worker.base_url, timeout=30, cookies=cookies)
    for _ in range(3):
        assert client.get(_GUARDED, follow_redirects=False).status_code == 200
    return client


def _seconds_until_rejected(client: httpx.Client, limit: float) -> float | None:
    """Seconds until *client* stops being let in, or ``None`` if it never is."""
    start = time.monotonic()
    while time.monotonic() - start < limit:
        if client.get(_GUARDED, follow_redirects=False).status_code in (302, 401):
            return time.monotonic() - start
        time.sleep(0.2)
    return None


class TestCrossProcessRevocation:
    def test_without_broadcasting_the_other_worker_stays_stale(self, pair):
        """The control: the bug, reproduced across two processes.

        If this ever starts failing, the treatment test below has stopped being
        evidence of anything — either the cache is no longer engaged on this
        path, or something else now invalidates it.
        """
        worker_a, worker_b = pair(False, "qa.control")
        revoker = _sign_in(worker_a)
        try:
            other = _warm(worker_b, dict(revoker.cookies))
            try:
                assert revoker.post(_REVOKE).status_code == 204
                assert _seconds_until_rejected(other, _OBSERVE_SECONDS) is None, (
                    "worker B saw the revocation without a transport — the cache is "
                    "not engaged, so the treatment test proves nothing"
                )
            finally:
                other.close()
        finally:
            revoker.close()

    def test_with_broadcasting_the_other_worker_stops_at_once(self, pair):
        """The treatment: the same setup, one setting different."""
        worker_a, worker_b = pair(True, "qa.treatment")
        revoker = _sign_in(worker_a)
        try:
            other = _warm(worker_b, dict(revoker.cookies))
            try:
                assert revoker.post(_REVOKE).status_code == 204
                elapsed = _seconds_until_rejected(other, _OBSERVE_SECONDS)
                assert elapsed is not None, (
                    "worker B kept honouring a revoked session; the broadcast did not arrive"
                )
                assert elapsed < _OBSERVE_SECONDS, elapsed
            finally:
                other.close()
        finally:
            revoker.close()
