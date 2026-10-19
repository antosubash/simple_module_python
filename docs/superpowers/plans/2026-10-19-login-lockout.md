# Login Lockout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make password-login lockout hold across workers, source IPs and restarts, and cover every password login route (GH #530).

**Architecture:** Tier 1 is an account lock stored on `users_user` (`failed_login_count`, `last_failed_login_at`, `locked_until`), bumped by one atomic `UPDATE … RETURNING` and locked through the ORM so the audit log sees it. Tier 2 is a per-IP-per-username throttle (plus an unknown-username counter) on the host's existing rate-limit `WindowStore`, which the framework now exposes as `app.state.sm.rate_limit_store`. One helper, `users/auth_local/lockout.py`, fronts `/api/users/auth/login` and `/api/users/auth/token`; the stock `/auth-inner` router and the in-process `LoginRateLimiter` go away.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy 2 async, Alembic, Redis (optional, via the host store), React + Inertia + vitest.

**Spec:** `docs/superpowers/specs/2026-10-19-login-lockout-design.md`

## Global Constraints

- New setting: `login_lockout_account_failures: int = Field(10, ge=1)` on `UsersSettings`.
- Existing settings keep their meaning: `login_rate_limit_failures` (5) is the tier-2 threshold, `login_rate_limit_window_seconds` (300) is the window for both tiers, `login_rate_limit_cooldown_seconds` (900) is the account lock length.
- Locked/throttled responses: HTTP 429, detail `"Too many attempts — try again later"`, `Retry-After` header (seconds, ≥ 1).
- `/auth/token` keeps its 401 `"Invalid credentials"`; `/auth/login` keeps its 400 `LOGIN_BAD_CREDENTIALS`; `LOGIN_USER_NOT_VERIFIED` (400) never counts as a failure.
- Store keys: `login:ip:<ip>:<username>` and `login:acct:<username>` (username lower-cased and stripped). No new Redis client.
- Migration: one revision in `host/migrations/versions/`, `down_revision = "b5018b617142"` (the head of the chain holding the users revisions), no `branch_labels`.
- `failed_login_count` and `last_failed_login_at` are excluded from audit diffs (`User.__audit_exclude_fields__`).
- Admin unlock: `PATCH /api/users/admin/{id}/unlock`, ORM write, guarded by `users.manage` like its siblings.
- 300-line cap on `.py`/`.ts`/`.tsx`; SQLModel only; framework never imports modules (SM009); every `.tsx` string through `t(keys…)`; test basenames globally unique (prefix `users_`).
- Commit messages end with `Claude-Session: https://claude.ai/code/session_01M9neheZZEe3sVpDi2S3zT4`.

## Review Focus

1. Case/whitespace variants of the username (`Alice@Example.com `) must hit the same counters and the same lock as `alice@example.com`, on both routes. → Task 3 test `test_username_variants_share_one_counter`.
2. Failure bookkeeping must survive the error response: the endpoint raises 400/401, the request session rolls back, and the count must still be there on the next request. → Task 4 test `test_failures_persist_across_requests` (the acceptance test also covers it).
3. A Redis outage must not turn login into a 500 nor drop the throttle: `peek` must fall back to per-worker counters exactly like `hit`. → Task 1 test `test_peek_falls_back_when_redis_down`.
4. A successful login of a different user must not reset someone else's counter, and a correct password during a lock must not reset the count. → Task 4 test `test_correct_password_while_locked_does_not_unlock`.
5. A lock that has expired must not show as locked in the admin UI, and must not refuse logins. → Task 5 test `test_expired_lock_is_not_reported` and Task 3 test `test_expired_lock_allows_login`.

---

### Task 1: Framework exposes the rate-limit store, with a non-counting `peek`

**Files:**
- Modify: `framework/core/simple_module_core/rate_limit.py` (protocol + `InProcessWindowStore.peek`)
- Modify: `framework/hosting/simple_module_hosting/_rate_limit.py` (`RedisWindowStore.peek`, shared `_eval`)
- Modify: `framework/core/simple_module_core/services.py` (`rate_limit_store` field)
- Modify: `framework/hosting/simple_module_hosting/_phase_helpers.py` (`install_middleware(..., rate_limit_store=)`)
- Modify: `framework/hosting/simple_module_hosting/app_builder.py` (build the store once, pass to both)
- Test: `framework/hosting/tests/test_rate_limit_store_shared.py`

**Interfaces:**
- Produces: `WindowStore.peek(key: str, spec: RateSpec) -> WindowResult` — reports the current window **without counting**; `allowed` means "one more hit would be within budget" (`count < spec.limit`); `retry_after` is seconds left in the window (0 when no window is live). `Services.rate_limit_store: WindowStore` (defaults to a fresh `InProcessWindowStore`). The same store instance backs `RateLimitMiddleware`.

- [ ] **Step 1: Write the failing tests**

```python
"""The host's rate-limit store is shared with modules (GH #530)."""

from __future__ import annotations

from simple_module_core.rate_limit import InProcessWindowStore, RateSpec
from simple_module_core.services import Services
from simple_module_hosting._rate_limit import RateLimitMiddleware, RedisWindowStore


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


async def test_peek_does_not_count() -> None:
    store = InProcessWindowStore(clock=_Clock())
    spec = RateSpec(2, 60)
    assert (await store.peek("k", spec)).count == 0
    await store.hit("k", spec)
    await store.hit("k", spec)
    first = await store.peek("k", spec)
    second = await store.peek("k", spec)
    assert (first.count, first.allowed) == (2, False)
    assert second.count == 2


async def test_peek_window_expires() -> None:
    clock = _Clock()
    store = InProcessWindowStore(clock=clock)
    spec = RateSpec(1, 60)
    await store.hit("k", spec)
    assert (await store.peek("k", spec)).retry_after == 60
    clock.now += 61
    result = await store.peek("k", spec)
    assert (result.count, result.allowed, result.retry_after) == (0, True, 0)


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def eval(self, script: str, numkeys: int, key: str, *args):
        if args:  # hit
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], args[0]]
        count = self.counts.get(key)
        return [0, -2] if count is None else [count, 30_000]


class _DeadRedis:
    async def eval(self, *a, **k):
        raise ConnectionError("redis down")


async def test_redis_peek_reads_without_counting() -> None:
    redis = _FakeRedis()
    store = RedisWindowStore(redis)
    spec = RateSpec(1, 60)
    assert (await store.peek("k", spec)).allowed is True
    await store.hit("k", spec)
    result = await store.peek("k", spec)
    assert (result.count, result.allowed, result.retry_after) == (1, False, 30)
    assert redis.counts == {"sm:rl:k": 1}


async def test_peek_falls_back_when_redis_down() -> None:
    store = RedisWindowStore(_DeadRedis())
    spec = RateSpec(1, 60)
    await store.hit("k", spec)  # counted by the per-worker fallback
    assert (await store.peek("k", spec)).allowed is False


def test_services_default_store() -> None:
    field = Services.__dataclass_fields__["rate_limit_store"]
    assert isinstance(field.default_factory(), InProcessWindowStore)


async def test_create_app_shares_one_store(app) -> None:
    store = app.state.sm.rate_limit_store
    node = app.middleware_stack
    while node is not None and not isinstance(node, RateLimitMiddleware):
        node = getattr(node, "app", None)
    assert node is not None and node.store is store
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_rate_limit_store_shared.py -q`
Expected: FAIL — `AttributeError: 'InProcessWindowStore' object has no attribute 'peek'`, `KeyError: 'rate_limit_store'`.

- [ ] **Step 3: Implement**

`simple_module_core/rate_limit.py`:

```python
class WindowStore(Protocol):
    async def hit(self, key: str, spec: RateSpec) -> WindowResult:
        """Count one request against *key* and report whether it is within budget."""
        ...

    async def peek(self, key: str, spec: RateSpec) -> WindowResult:
        """Report *key*'s current window without counting.

        ``allowed`` answers "would one more hit be within budget", so a caller
        can refuse before doing work and count only what failed.
        """
        ...


class InProcessWindowStore:
    async def peek(self, key: str, spec: RateSpec) -> WindowResult:
        now = self._clock()
        entry = self._windows.get(key)
        if entry is None or entry[0] <= now * 1000:
            return WindowResult(allowed=spec.limit > 0, retry_after=0, count=0)
        end_ms, count = entry
        retry = max(1, math.ceil(end_ms / 1000 - now))
        return WindowResult(allowed=count < spec.limit, retry_after=retry, count=count)
```

`simple_module_hosting/_rate_limit.py` — factor the Redis call and its fail-open handling into `_eval`, add the read-only script:

```python
_PEEK_LUA = """
local c = redis.call('GET', KEYS[1])
if not c then return {0, 0} end
return {tonumber(c), redis.call('PTTL', KEYS[1])}
"""

    async def _eval(self, script: str, key: str, *args: Any) -> Any:
        """Run *script* on *key*; ``None`` means "use the per-worker fallback"."""
        if self._clock() < self._down_until:
            return None
        try:
            return await self._client.eval(script, 1, _KEY_PREFIX + key, *args)
        except Exception as exc:
            now = self._clock()
            self._down_until = now + _BACKOFF
            if now - self._last_warn >= _WARN_EVERY:
                self._last_warn = now
                logger.warning(
                    "Rate limiter Redis unavailable (%s); using per-worker counters", exc
                )
            return None

    async def hit(self, key: str, spec: RateSpec) -> WindowResult:
        reply = await self._eval(_LUA, key, spec.period * 1000)
        if reply is None:
            return await self._fallback.hit(key, spec)
        count, pttl = int(reply[0]), int(reply[1])
        retry = max(1, -(-pttl // 1000)) if pttl > 0 else spec.period
        return WindowResult(allowed=count <= spec.limit, retry_after=retry, count=count)

    async def peek(self, key: str, spec: RateSpec) -> WindowResult:
        reply = await self._eval(_PEEK_LUA, key)
        if reply is None:
            return await self._fallback.peek(key, spec)
        count, pttl = int(reply[0]), int(reply[1])
        retry = max(1, -(-pttl // 1000)) if pttl > 0 else 0
        return WindowResult(allowed=count < spec.limit, retry_after=retry, count=count)
```

`services.py` — new field after `view_prefixes`:

```python
    #: The store behind ``RateLimitMiddleware`` (Redis when ``SM_REDIS_URL`` is
    #: set), shared so a module throttling its own events — the users login
    #: lockout — counts in the same place across workers instead of opening a
    #: second Redis client. Defaulted for apps built outside ``create_app``.
    rate_limit_store: WindowStore = field(default_factory=InProcessWindowStore)
```

with `from simple_module_core.rate_limit import InProcessWindowStore, WindowStore` at runtime import level.

`_phase_helpers.install_middleware` gains a keyword `rate_limit_store: WindowStore` and passes `store=rate_limit_store`; `app_builder.create_app` builds `rate_limit_store = build_store(settings.redis_url)` just before Phase 8, passes it to `install_middleware` and to `Services(rate_limit_store=rate_limit_store)`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest framework/hosting/tests/test_rate_limit_store_shared.py framework/hosting/tests/test_request_guard_rate_limit.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `feat(hosting): share the rate-limit store on app.state.sm (#530)`

---

### Task 2: Lockout columns on `users_user` + migration + audit exclusions

**Files:**
- Modify: `modules/users/users/models/user.py`
- Create: `host/migrations/versions/c8e4f1a2b6d9_users_login_lockout.py`
- Test: `modules/users/tests/test_users_lockout_columns.py`

**Interfaces:**
- Produces: `User.failed_login_count: int` (server default `0`), `User.last_failed_login_at: datetime | None`, `User.locked_until: datetime | None` (all `AwareDateTime`); `User.__audit_exclude_fields__ = {"failed_login_count", "last_failed_login_at"}`.

- [ ] **Step 1: Write the failing test**

```python
"""Lockout columns on users_user (GH #530)."""

from __future__ import annotations

from datetime import UTC, datetime

from simple_module_db.audit import snapshot_changes
from sqlalchemy import select
from users.models import User


async def test_new_user_starts_unlocked(users_db) -> None:
    user = (await users_db.execute(select(User).limit(1))).scalar_one()
    assert user.failed_login_count == 0
    assert user.last_failed_login_at is None
    assert user.locked_until is None


async def test_counter_fields_are_not_audited(users_db) -> None:
    user = (await users_db.execute(select(User).limit(1))).scalar_one()
    user.failed_login_count = 3
    user.last_failed_login_at = datetime.now(UTC)
    assert snapshot_changes(users_db.sync_session, None, None) == []
    user.locked_until = datetime.now(UTC)
    [record] = snapshot_changes(users_db.sync_session, None, None)
    assert [c["field"] for c in record.changes] == ["locked_until"]
```

(Adjust the change-dict key to whatever `snapshot_changes` emits — read `framework/db/simple_module_db/audit.py` first.)

- [ ] **Step 2: Run** `uv run pytest modules/users/tests/test_users_lockout_columns.py -q` — Expected: FAIL (`AttributeError: failed_login_count`).

- [ ] **Step 3: Implement** — on `User`:

```python
    # Login lockout (GH #530). The counter is bumped by one atomic UPDATE per
    # failed password login, restarting once ``last_failed_login_at`` is older
    # than the window; reaching the threshold stamps ``locked_until`` through
    # the ORM so the lock is audited. See ``users.auth_local.lockout``.
    failed_login_count: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    last_failed_login_at: datetime | None = Field(default=None, sa_type=AwareDateTime())
    locked_until: datetime | None = Field(default=None, sa_type=AwareDateTime())

    # Every wrong password writes these two; auditing them would bury the
    # lock/unlock rows that matter under one row per failed attempt.
    __audit_exclude_fields__: ClassVar[set[str]] = {"failed_login_count", "last_failed_login_at"}
```

Migration:

```python
"""users: login lockout columns (GH #530)

Revision ID: c8e4f1a2b6d9
Revises: b5018b617142
"""

revision: str = "c8e4f1a2b6d9"
down_revision: str | None = "b5018b617142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users_user",
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "users_user", sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users_user", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users_user", "locked_until")
    op.drop_column("users_user", "last_failed_login_at")
    op.drop_column("users_user", "failed_login_count")
```

- [ ] **Step 4: Verify** — the test passes; on a scratch SQLite file: `SM_DATABASE_URL=sqlite+aiosqlite:////tmp/claude-1001/lockout/m.db uv run --project host alembic -c host/alembic.ini upgrade heads` then `… check` (only the known `users_access_token.expires_at` drift may remain); `make migrations-roundtrip-pg` with `SM_MIGRATIONS_PG_URL` on a disposable DB if Postgres is reachable.

- [ ] **Step 5: Commit** — `feat(users): lockout columns on users_user (#530)`

---

### Task 3: Lockout service `users/auth_local/lockout.py`

**Files:**
- Create: `modules/users/users/auth_local/lockout.py`
- Modify: `modules/users/users/settings.py` (`login_lockout_account_failures`)
- Test: `modules/users/tests/test_users_lockout_service.py`

**Interfaces:**
- Consumes: `app.state.sm.rate_limit_store` (`hit`/`peek`, Task 1); `User` columns (Task 2).
- Produces:
  - `LOCKED_DETAIL = "Too many attempts — try again later"`
  - `LoginAttempt(username, ip, store, settings, now)` (frozen dataclass); `LoginAttempt.build(username, ip, store, settings, now)` lower-cases and strips the username
  - `login_attempt(request: Request, username: str) -> LoginAttempt`
  - `async refused_for(session, attempt) -> int | None` — seconds to wait, `None` to proceed
  - `async record_failure(session, attempt) -> None` — commits the session
  - `async record_success(session, user_id) -> None` — no commit (rides the request's unit of work)
  - `too_many_attempts(retry_after: int) -> HTTPException`
  - module-level `_utcnow()` — the clock; tests monkeypatch it or build `LoginAttempt` with an explicit `now`.

- [ ] **Step 1: Write the failing tests** (`users_db` + a `_settings(**overrides)` helper building `UsersSettings`, an `InProcessWindowStore`, `LoginAttempt` built directly with explicit `now`):

```python
async def test_account_locks_at_threshold(users_db, alice) -> None:
    attempt = _attempt("alice@example.com", now=T0, account=3)
    for _ in range(3):
        await record_failure(users_db, attempt)
    await users_db.refresh(alice)
    assert alice.locked_until == T0 + timedelta(seconds=900)
    assert alice.failed_login_count == 0
    assert await refused_for(users_db, attempt) == 900


async def test_expired_window_restarts_count(users_db, alice) -> None:
    await record_failure(users_db, _attempt("alice@example.com", now=T0))
    await record_failure(users_db, _attempt("alice@example.com", now=T0 + timedelta(seconds=301)))
    await users_db.refresh(alice)
    assert alice.failed_login_count == 1


async def test_expired_lock_allows_login(
    users_db, alice
) -> None: ...  # lock at T0, refused_for at T0+901s is None


async def test_success_resets_count(
    users_db, alice
) -> None: ...  # two failures, record_success, count 0 and last_failed_login_at None


async def test_ip_throttle_after_tier2_limit(users_db, alice) -> None:
    store = InProcessWindowStore()
    for _ in range(5):
        await record_failure(users_db, _attempt("alice@example.com", ip="1.1.1.1", store=store))
    assert await refused_for(users_db, _attempt("alice@example.com", ip="1.1.1.1", store=store))
    assert (
        await refused_for(users_db, _attempt("alice@example.com", ip="2.2.2.2", store=store))
        is None
    )


async def test_unknown_username_counts_against_account_threshold(
    users_db,
) -> None: ...  # 10 failures for ghost@example.com from 10 IPs → refused_for is not None


async def test_username_variants_share_one_counter(
    users_db, alice
) -> None: ...  # failures as " Alice@Example.COM " and "alice@example.com" add up on one row
```

- [ ] **Step 2: Run** — Expected: FAIL (`ModuleNotFoundError: users.auth_local.lockout`).

- [ ] **Step 3: Implement** — settings:

```python
    # Rate limit (login). ``login_rate_limit_failures`` throttles one source
    # (IP + username) on the shared rate-limit store; the account threshold
    # locks the account itself, whichever networks the failures come from.
    # 10 rather than 5: anyone who knows an address could otherwise lock its
    # owner out. ``…_cooldown_seconds`` is how long that lock lasts.
    login_rate_limit_failures: int = 5
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_cooldown_seconds: int = 900
    login_lockout_account_failures: int = Field(10, ge=1)
```

`lockout.py` core:

```python
def _by_username(username: str) -> Any:
    return func.lower(User.email) == username


async def refused_for(session: AsyncSession, attempt: LoginAttempt) -> int | None:
    waits: list[int] = []
    stmt = select(User.locked_until).where(_by_username(attempt.username))
    for locked_until in (await session.execute(stmt)).scalars():
        if locked_until is not None and locked_until > attempt.now:
            waits.append(math.ceil((locked_until - attempt.now).total_seconds()))
    for key, spec in attempt.store_checks():
        result = await attempt.store.peek(key, spec)
        if not result.allowed:
            waits.append(result.retry_after)
    return max(waits) if waits else None


async def record_failure(session: AsyncSession, attempt: LoginAttempt) -> None:
    s = attempt.settings
    await attempt.store.hit(attempt.ip_key, attempt.ip_spec)
    window_start = attempt.now - timedelta(seconds=s.login_rate_limit_window_seconds)
    stale = User.last_failed_login_at.is_(None) | (User.last_failed_login_at < window_start)
    stmt = (
        update(User)
        .where(_by_username(attempt.username))
        .values(
            failed_login_count=case((stale, 1), else_=User.failed_login_count + 1),
            last_failed_login_at=attempt.now,
            updated_at=User.updated_at,  # a failed sign-in is not an edit of the account
        )
        .returning(User.id, User.failed_login_count)
        .execution_options(synchronize_session=False)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        await attempt.store.hit(attempt.account_key, attempt.account_spec)
    for user_id, count in rows:
        if count >= s.login_lockout_account_failures:
            user = await session.get(User, user_id, populate_existing=True)
            user.locked_until = attempt.now + timedelta(seconds=s.login_rate_limit_cooldown_seconds)
            user.failed_login_count = 0
    await session.commit()


async def record_success(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .where((User.failed_login_count != 0) | User.last_failed_login_at.is_not(None))
        .values(failed_login_count=0, last_failed_login_at=None, updated_at=User.updated_at)
        .execution_options(synchronize_session=False)
    )


def too_many_attempts(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=LOCKED_DETAIL,
        headers={"Retry-After": str(max(1, retry_after))},
    )
```

- [ ] **Step 4: Run** `uv run pytest modules/users/tests/test_users_lockout_service.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat(users): login lockout service backed by the DB and the shared store (#530)`

---

### Task 4: Wire both login routes; drop `/auth-inner` and `LoginRateLimiter`

**Files:**
- Modify: `modules/users/users/auth_local/api.py` (login uses lockout; remove `/auth-inner` mount and `get_rate_limiter`)
- Modify: `modules/users/users/auth_local/token_api.py` (token login uses lockout)
- Modify: `modules/users/users/auth_local/rate_limit.py` (delete `LoginRateLimiter`, fix module docstring)
- Modify: `modules/users/users/startup.py`, `modules/users/users/state.py` (drop `rate_limiter`)
- Modify: `modules/users/tests/test_rate_limit.py` (drop `LoginRateLimiter` tests), `modules/users/tests/_users_app_builders.py` (`database_url`/`overrides` params, `redis_url=None`)
- Modify: comments naming `LoginRateLimiter` in `self_account.py`, `tests/test_profile_password.py`, `modules/site_lock/site_lock/rate_limit.py`
- Test: `modules/users/tests/test_users_login_lockout.py`

**Interfaces:**
- Consumes: Task 3's `login_attempt`, `refused_for`, `record_failure`, `record_success`, `too_many_attempts`.
- Produces: `_build_users_app(monkeypatch, *, allow_signup, seed_admin=True, database_url="sqlite+aiosqlite:///:memory:", overrides=None)`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_acceptance_three_ips_two_apps_survives_restart(monkeypatch, tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'lockout.db'}"
    overrides = {"login_lockout_account_failures": ("5", "int")}
    app_a, ctx_a = await _build_users_app(monkeypatch, allow_signup=False, database_url=url, overrides=overrides)
    app_b, ctx_b = await _build_users_app(monkeypatch, allow_signup=False, database_url=url, overrides=overrides)
    await _make_standard_user(app_a, "alice@example.com")
    plan = [(app_a, "1.1.1.1"), (app_b, "2.2.2.2"), (app_a, "3.3.3.3"), (app_b, "1.1.1.1"), (app_a, "2.2.2.2")]
    for app, ip in plan:
        r = await _login(app, ip, "alice@example.com", "wrong")
        assert r.status_code == 400
    r = await _login(app_b, "9.9.9.9", "alice@example.com", "UserPass1!")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # fresh app, same DB file
    app_c, ctx_c = await _build_users_app(monkeypatch, allow_signup=False, database_url=url, overrides=overrides)
    assert (await _login(app_c, "8.8.8.8", "alice@example.com", "UserPass1!")).status_code == 429
    r = await _token(app_c, "8.8.8.8", "alice@example.com", "UserPass1!")
    assert r.status_code == 429


async def test_unknown_and_locked_look_the_same(...)        # same status + detail
async def test_token_bad_credentials_still_401(...)          # 401 "Invalid credentials" until throttled, then 429
async def test_failures_persist_across_requests(...)         # failed_login_count in DB after 2 bad logins
async def test_correct_password_while_locked_does_not_unlock(...)
async def test_success_resets_count(...)                     # 2 bad, 1 good → count 0
async def test_auth_inner_login_is_gone(anon_client)          # POST /api/users/auth-inner/login → 404/405
async def test_tier2_throttles_ip_not_account(...)            # 5 bad from IP A → 6th from A 429, IP B → 400
```

- [ ] **Step 2: Run** — Expected: FAIL (counts don't persist across apps; `/auth/token` never 429s; `/auth-inner/login` still answers).

- [ ] **Step 3: Implement** — `login()`:

```python
    db: AsyncSession = Depends(get_db),
):
    attempt = login_attempt(request, credentials.username)
    if (wait := await refused_for(db, attempt)) is not None:
        raise too_many_attempts(wait)
    ... authenticate ...
    if user is None or not user.is_active:
        await record_failure(db, attempt)
        raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")
    ... verification check (unchanged, not counted) ...
    await record_success(db, user.id)
```

`token_login()` — same shape around its existing checks: refuse first; `record_failure` before each 401; `record_success` once the password verified and the verification check passed.

Remove the `auth_inner` include (the wrappers own `/auth/login` and `/auth/logout`; grep showed no callers of `/auth-inner` in code, tests, docs or JS). Delete `LoginRateLimiter`, `get_rate_limiter`, `UsersState.rate_limiter` and its construction in `_build_limiters`.

- [ ] **Step 4: Run** `uv run pytest modules/users/tests -q -n 8` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat(users): lock accounts across workers and IPs on both login routes (#530)`

---

### Task 5: Admin unlock + locked state in the UI

**Files:**
- Modify: `modules/users/users/contracts/schemas.py` (`UserListItem.locked_until`)
- Modify: `modules/users/users/admin/queries.py` (`to_list_item` reports only a live lock)
- Modify: `modules/users/users/admin/service.py` (`unlock`)
- Modify: `modules/users/users/admin/api.py` (`PATCH /{user_id}/unlock`)
- Modify: `modules/users/users/admin/components/user-list-item.ts`, `UserRow.tsx`, `UserCards.tsx`, `StatusPill.tsx` (`LockedBadge`)
- Modify: `modules/users/users/pages/Users/Edit.tsx`, `components/AccountCard.tsx`, `components/useUserActions.ts`
- Modify: `modules/users/users/locales/en.json`; regenerate `packages/i18n/src/*.generated*.ts` with `make gen-i18n`
- Test: `modules/users/tests/test_users_admin_unlock.py`, `modules/users/tests-js/AccountCardLocked.test.tsx`

**Interfaces:**
- Consumes: Task 2 columns; Task 3 `record_failure` (to lock in tests).
- Produces: `UserService.unlock(user_id) -> User`; `UserListItem.locked_until: datetime | None` (None when not locked *now*); TS `UserListItem.locked_until?: string | null`; `useUserActions(...).lockedUntil`, `.unlock()`, `.savingUnlock`; `AccountCard` props `lockedUntil: string | null`, `savingUnlock: boolean`, `onUnlock: () => void`; `<LockedBadge />`.

New i18n keys (`users` namespace): `metadata_card.locked_until` "Locked until", `account_status.unlock_button` "Unlock", `edit.toast_unlocked` "Account unlocked", `edit.toast_unlock_failed` "Could not unlock the account", `user_row.locked_badge` "locked".

- [ ] **Step 1: Write the failing tests**

```python
async def test_unlock_clears_lock_and_is_audited(users_app, admin_client) -> None:
    # lock alice via record_failure ×10, then:
    r = await admin_client.patch(f"/api/users/admin/{alice_id}/unlock")
    assert r.status_code == 200 and r.json()["locked_until"] is None
    # DB: locked_until/failed_login_count/last_failed_login_at cleared
    # audit_log: an "updated" entry with locked_until for the lock and one for the unlock;
    # no entry whose only changes are failed_login_count / last_failed_login_at


async def test_list_reports_locked_until(...)       # GET /api/users/admin → locked_until set
async def test_expired_lock_is_not_reported(...)    # locked_until in the past → None
async def test_unlock_requires_manage(user_client)  # 403
```

```tsx
// tests-js/AccountCardLocked.test.tsx
test('shows Locked until and calls onUnlock', () => {
  const onUnlock = vi.fn();
  render(<AccountCard {...base} lockedUntil="2026-10-19T12:00:00Z" onUnlock={onUnlock} />);
  expect(screen.getByText('Locked until')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
  expect(onUnlock).toHaveBeenCalled();
});
test('no lock row when unlocked', () => { ... lockedUntil={null} → queryByText('Locked until') is null });
```

- [ ] **Step 2: Run** — Expected: FAIL (404 on `/unlock`; no `locked_until` key; no "Locked until").

- [ ] **Step 3: Implement**

```python
    async def unlock(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        user.locked_until = None
        user.failed_login_count = 0
        user.last_failed_login_at = None
        await self._db.flush()
        return user
```

```python
@admin_router.patch("/{user_id}/unlock", response_model=UserListItem)
async def admin_unlock_user(user_id: uuid.UUID, service: UserService = Depends(get_user_service)):
    """Lift a login lockout early. An ORM write, so the audit log records it."""
    try:
        user = await service.unlock(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    return service.to_list_item(user)
```

`to_list_item`: `locked_until=_live_lock(user.locked_until)` where `_live_lock` returns the value only when it is after `datetime.now(UTC)`.

`AccountCard`: when `lockedUntil` is set, a `Row` labelled `t(keys.users.metadata_card.locked_until)` showing `formatDateTime`-style local time plus an outline `Button` `t(keys.users.account_status.unlock_button)` calling `onUnlock`. `useUserActions` gains `lockedUntil` state (initialised from the prop) and `unlock()` (PATCH `/api/users/admin/${userId}/unlock`, toast, set `null`). `UserRow`/`UserCards` render `<LockedBadge />` next to the status pill when `user.locked_until` is set.

- [ ] **Step 4: Run** `uv run pytest modules/users/tests/test_users_admin_unlock.py -q`, `npx vitest run modules/users/tests-js/AccountCardLocked.test.tsx`, `make gen-i18n`, `make ci-check-untranslated` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat(users): admin unlock and locked state in the users UI (#530)`

---

### Task 6: Docs + CHANGELOG

**Files:**
- Modify: `docs/modules/users.md` (lockout section, settings table, admin endpoint, remove the in-process-counter note)
- Modify: `docs/framework/request-guards.md` (§ Not covered → the store is shared as `app.state.sm.rate_limit_store`; `peek`)
- Modify: `CHANGELOG.md` `[Unreleased]`

- [ ] **Step 1: Write** — `CHANGELOG.md`:

```markdown
### Changed
- **Behaviour change (#530):** password-login lockout now holds across workers,
  source IPs and restarts. Ten failures for one account (from anywhere) within
  `login_rate_limit_window_seconds` lock it for `login_rate_limit_cooldown_seconds`
  — the right password included — answering 429 with `Retry-After`. Five
  failures from one IP for one username throttle that source for the window.
  New setting `users.login_lockout_account_failures` (default 10). Counters live
  on `users_user` and on the host rate-limit store (Redis when `SM_REDIS_URL`
  is set); a migration adds three columns.
- **Behaviour change (#530):** `POST /api/users/auth/token` is now covered by the
  same lockout and throttle (429 when locked; bad credentials still 401).
- **Behaviour change (#530):** the stock fastapi-users router at
  `/api/users/auth-inner/*` is no longer mounted; use `/api/users/auth/login`
  and `/api/users/auth/logout`.

### Added
- `PATCH /api/users/admin/{id}/unlock` lifts a lockout (audited); the user list
  shows a "locked" badge and the edit page a "Locked until" row with Unlock.
- `app.state.sm.rate_limit_store` and `WindowStore.peek()`.
```

- [ ] **Step 2: Verify** — `uv run ruff format --check docs/` and `make lint`.

- [ ] **Step 3: Commit** — `docs(users): document login lockout (#530)`

---

## Final verification

`rmdir /tmp/.git 2>/dev/null`; `uv run pytest -q -n 8`, `make test-js`, `make lint`, `make ci-check-untranslated`, `make doctor` — each redirected to `/tmp/claude-1001/lockout/<name>.log` with the real exit code recorded.
