# QA plan — `InvalidationBus` cross-worker cache invalidation

**Date:** 2026-09-19
**Under test:** PR #330 / issue #318 — `simple_module_core.invalidation`,
`background_tasks.invalidation`, `users.session_revocation`, and the boot wiring
that connects them.
**Baseline:** `claude/github-issues-8yxn4q` @ 398a5af (CI green, 3073 passed).

## Why this plan exists

The shipped test suite is 43 tests and it is green, but it does not test the
thing the feature is for. Every transport test runs against a **fake Redis
client**, and every "another worker hears it" test runs **two buses inside one
process**. The claim on the tin — *a revocation in worker A stops worker B
honouring the session* — is therefore asserted nowhere.

That is not a cosmetic gap. Two whole classes of defect live in it:

- Anything where the fake and real redis-py disagree (frame shape, `data` type,
  `from_url` kwargs, `aclose` semantics). The transport wraps its teardown in
  `contextlib.suppress(Exception)`, so a wrong method name there is *invisible*.
- Anything in the path between an HTTP request and a `publish` call. Every
  existing test calls `publish_revocation` directly, so deleting the
  `db.on_commit(...)` line from both endpoints would leave the suite green.

This plan closes those, then works down a ranked list of smaller gaps.

## Method

Four layers, each answering a question the layer below cannot:

| Layer | Question | Fake or real |
|---|---|---|
| Unit — bus | Does the fan-out, wire format and origin filter behave? | n/a |
| Unit — transport | Does *this file's* logic (retry, timeout, teardown) behave? | fake client |
| Integration — real Redis | Does redis-py actually do what the fake pretends? | real `redis-server` |
| Integration — two processes | Does a revocation in one OS process reach another? | real Redis + shared SQLite file |

The last two are new. A `redis_server` fixture starts a throwaway
`redis-server` on a free port (`--save '' --appendonly no`), so the tests need
no external service and no `docker-up`; they skip with a loud reason when the
binary is absent. `redis-server` is present on GitHub's `ubuntu-latest` image,
so these run in the existing `Python tests` job — **verified by comparing the
CI test count, not assumed.**

## Contract → coverage → gap

Legend: ✅ covered before this plan · 🆕 added by this plan · ⬜ deliberately not tested.

### The bus (`simple_module_core.invalidation`)

| # | Claim | Status |
|---|---|---|
| B1 | `publish` runs subscribers on that channel only | ✅ |
| B2 | sync and async handlers both run | ✅ |
| B3 | one failing handler does not starve the others | ✅ |
| B4 | `publish` with no subscribers is a no-op | ✅ |
| B5 | `publish` forwards the encoded invalidation to the transport | ✅ |
| B6 | a transport failure never propagates; the local effect stands | ✅ |
| B7 | `clear_transport` drops back to in-process | ✅ |
| B8 | `deliver` runs handlers for a remote message | ✅ |
| B9 | a bus ignores its own broadcast echoed back | ✅ |
| B10 | `bytes` payloads are accepted | ✅ |
| B11 | malformed JSON / wrong version / bad types are dropped, not raised | ✅ |
| B12 | `key=None` survives the round trip as `None` | ✅ |
| B13 | two buses never share an origin | ✅ |
| B14 | **non-UTF-8 bytes are dropped, not raised** | 🆕 |
| B15 | **a worker with no subscribers on a channel still relays it to the transport** | 🆕 |
| B16 | **a remote message on an unsubscribed channel is a silent no-op** | 🆕 |

B15 matters because it is a design decision nothing recorded: a worker that
does not itself cache `session_version` must still forward the bump, or a
heterogeneous fleet loses messages depending on which worker served the write.

### The Redis transport (`background_tasks.invalidation`)

| # | Claim | Status |
|---|---|---|
| T1 | `publish` reaches the configured channel | ✅ fake |
| T2 | `publish` before `start` raises a clear error | ✅ |
| T3 | a hung broker is bounded by `PUBLISH_TIMEOUT_SECONDS` | ✅ fake |
| T4 | a failing publish does not reach the caller | ✅ fake |
| T5 | an inbound message is delivered to the bus | ✅ fake |
| T6 | non-`message` frames are ignored | ✅ fake |
| T7 | the listener reconnects after a failure and warns once | ✅ fake |
| T8 | `stop` cancels the listener, closes the client, is idempotent | ✅ fake |
| T9 | **against real Redis: publish → subscribe round trip delivers** | 🆕 |
| T10 | **against real Redis: two transports, A publishes, B applies, A does not** | 🆕 |
| T11 | **against real Redis: `stop` really releases the connection** | 🆕 |
| T12 | **a refused connection fails the publish without breaking the local eviction** | 🆕 |
| T13 | **a broker that accepts and then answers nothing is bounded by the publish timeout** | 🆕 |
| T14 | **only the configured channel is subscribed (two apps, one Redis database)** | 🆕 |

T13 is the one with teeth and T12 is explicitly *not* — see F5. A refused
connection fails instantly and would pass with no timeout at all; only a mute
socket exercises the bound.

### Boot wiring (`background_tasks.module`, `app_builder`, `Services`)

| # | Claim | Status |
|---|---|---|
| W1 | `broadcast_invalidations=false` installs no transport | ✅ |
| W2 | `broadcast_invalidations=true` installs one | ✅ fake |
| W3 | **`on_shutdown` clears the bus transport and stops the listener** | 🆕 |
| W4 | **an unreachable Redis URL still lets `on_startup` complete** | 🆕 |
| W5 | `create_app` puts the same bus on `Services` that it passed to the hook | ✅ |
| W6 | **two `Services` instances do not share one bus (default-factory isolation)** | 🆕 |
| W7 | **SM007 does not flag a module whose only hook is `register_invalidations`** | 🆕 |

W7 is a regression guard on a list I edited. W6 guards the classic mutable-default
bug: a shared bus would leak subscribers between test apps and look like
flakiness.

### `users` revocation (`users.session_revocation`)

| # | Claim | Status |
|---|---|---|
| U1 | a string wire key evicts a `uuid.UUID`-keyed entry | ✅ |
| U2 | a non-UUID key does not raise | ✅ |
| U3 | `key=None` clears the whole cache | ✅ |
| U4 | the revoking worker drops its own entry | ✅ |
| U5 | a second bus applies the broadcast | ✅ |
| U6 | no bus → local eviction fallback | ✅ |
| U7 | `UsersModule.register_invalidations` subscribes the channel | ✅ |
| U8 | `create_app` calls the hook | ✅ |
| U9 | **`POST /api/users/me/sessions/revoke-all` publishes on the bus** | 🆕 |
| U10 | **`POST /api/users/me/password` publishes on the bus** | 🆕 |
| U11 | **a request that fails after the bump does NOT publish** | 🆕 |
| U12 | **two OS processes, one Redis, one DB: revoking in A strands the session in B** | 🆕 |

U9–U11 are the "did anyone actually wire the endpoint" guards. U12 is the
feature's headline claim, tested end to end for the first time.

### Settings surface

| # | Claim | Status |
|---|---|---|
| S1 | `broadcast_invalidations` defaults true, env override works | ✅ |
| S2 | `invalidation_channel` defaults namespaced, env override works | ✅ |
| S3 | **an empty channel name is rejected (`min_length=1`)** | 🆕 |
| S4 | **both fields reach the settings admin surface with the right `env_var` labels** | 🆕 |

S4 asserts through `collect_module_settings` — what the settings screens and
`import-from-env` actually read — rather than through `model_fields`, which
would only restate the dataclass to itself.

### Deliberately not tested

| Claim | Why |
|---|---|
| ⬜ Behaviour across a genuine multi-host Redis | No second host. U12's two processes cover the process boundary, which is the one the bug lived at. |
| ⬜ Redis auth / TLS URLs | `from_url` is redis-py's contract, not ours. |
| ⬜ Celery worker participation | Documented non-goal: a standalone worker builds no app and installs no transport. |
| ⬜ Message ordering under concurrent revocations | The counter is monotonic in the DB and the cache only ever drops entries, so a reordered pair converges to the same state. Worth a note, not a test. |
| ⬜ Load behaviour of the pub/sub channel | Volume is one message per revocation; a benchmark would measure Redis, not this code. |

## Risk ranking

| Rank | Gap | If it is broken | Detected by |
|---|---|---|---|
| P0 | endpoints don't publish | the feature does nothing in production, suite stays green | U9, U10 |
| P0 | real cross-process delivery | the headline claim is false | U12 |
| P0 | fake/real redis-py divergence | silently swallowed by `suppress(Exception)` | T9–T11 |
| P1 | `on_shutdown` leaks the listener | a reloading dev server accumulates tasks | W3 |
| P1 | rollback still broadcasts | other workers drop a cache entry for a write that never happened | U11 |
| P1 | SM007 regression | a legitimate module reported as hook-less | W7 |
| P1 | shared default bus | cross-test subscriber leakage read as flake | W6 |
| P2 | no-subscriber worker swallows a relay | heterogeneous fleets lose messages | B15 |
| P2 | unbounded connect | a black-hole broker hangs a boot | T12 |
| P2 | settings not surfaced / empty channel accepted | operator can't configure, or subscribes to `""` | S3, S4 |

## Exit criteria

1. Every 🆕 row above implemented and passing.
2. `uv run pytest` green, and the new integration tests **confirmed to have run,
   not skipped** (assert on the collected count, and check the CI log).
3. `make lint`, `ty`, the 300-line cap and `make doctor` clean.
4. An independent adversarial pass (QA agents) over the same contract, finding
   no P0/P1 defect that this plan's tests miss. Anything it finds is either
   fixed or recorded here with a reason.

## Findings

Recorded as they were established. The first three came out of writing the tests
rather than out of running them, which is the usual way.

### F1 — the two-process claim was never true in the suite (P0, fixed)

`test_invalidation_cross_process.py` now proves it, and its control arm
reproduces the bug: with `broadcast_invalidations=false` and a 300-second cache
TTL, worker B kept honouring a revoked session for the full observation window;
with broadcasting on it stopped in under 0.1s. Nothing but the broadcast
distinguishes the two runs.

Two drafts of that test passed while measuring nothing, which is worth recording
because both failure modes are easy to repeat:

- A fresh HTTP client per request discards the cookie the worker writes back, and
  the `session_version` cache is only consulted on the *cached-context* path —
  which that cookie is what engages. Every request did a full user load instead,
  so both arms looked identical and "passed".
- The cache TTL override was spelled `SM_USERS_SESSION_VERSION_TTL_SECONDS`,
  which matches no field (see F2), so the TTL stayed at its 30-second default.

This is why the control arm is a permanent test and not a one-off check.

### F2 — a documented operator knob that never worked (P1, fixed)

`session_version_cache.py` told operators to shorten the revocation window with
`SM_USERS_SESSION_VERSION_TTL_SECONDS`. The field is
`session_version_cache_ttl_seconds`, so the variable name was wrong; and
`UsersSettings` is a `DbBackedSettings`, which strips the environment source
entirely, so *no* `SM_USERS_*` variable reaches it directly. Verified:
`SM_USERS_SESSION_VERSION_CACHE_TTL_SECONDS=5` still yields `30`.

The real path is the settings store — the admin UI, or the correctly-named
variable plus `smpy settings import-from-env`. Docstring and changelog corrected.

### F3 — a stored override beats the environment (P1, reported, not fixed here)

`settings.hydrate.hydrate_settings` does `cls(**parsed)` with the DB values, and
pydantic-settings ranks **init args above its env source**. So for any
env-readable module settings class — `BackgroundTasksSettings`, including
`broker_url` — a row in the settings store silently wins over the environment
from boot hydration onwards. Verified directly:

```
SM_BG_TASKS_BROADCAST_INVALIDATIONS=true  →  True
  … plus a stored override of False       →  False
```

This inverts the precedence CLAUDE.md states as an invariant (`env → DB →
default`, "env must keep winning or existing deployments change behaviour
silently on upgrade"). It is pre-existing and not specific to this feature, so it
is documented in `docs/framework/invalidation.md` and left for its own change
rather than fixed inside this PR — changing the precedence alters behaviour for
every existing deployment that has both set, which is the repo owner's call.

### F4 — concurrent first boot races on the admin/role seed (P2, reported)

Two worker processes reaching a freshly-migrated database at the same time both
try to seed the bootstrap admin and its roles; one dies with
`IntegrityError: UNIQUE constraint failed: users_role.name` and `Application
startup failed`. Reproduced twice while building the two-process fixture, which
now boots workers sequentially to avoid it. Unrelated to invalidation — it is in
`users.bootstrap` — but it is a real first-boot failure for any multi-worker
deployment (gunicorn `-w 2`, two replicas, a rolling deploy onto an empty
database). CLAUDE.md already requires this of the secret key ("atomically —
concurrent workers must converge"); the role seed does not do the same.

### F5 — a test that passed for the wrong reason (P2, fixed)

The first real-Redis "unreachable broker" test pointed at a black-hole address
and asserted the publish returned. A refused connection fails instantly, so it
passed with or without any timeout. Replaced with a server that accepts the
connection and then answers nothing, which is the failure mode the publish
timeout actually exists for, and mutation-checked: removing
`asyncio.timeout(PUBLISH_TIMEOUT_SECONDS)` makes it fail.
