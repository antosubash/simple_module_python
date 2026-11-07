# Warm the invalidation publish connection (GH #880)

## Goal and scope

A publish on `RedisInvalidationTransport` runs inside `asyncio.timeout(PUBLISH_TIMEOUT_SECONDS)`
(1 s), in the response cycle of the request that made the write. The client's command
connection is opened lazily by the first command, so the first publish after boot, or after
Redis came back from an outage, also pays the TCP connect and handshake inside that second.
Under load the connect is cancelled (seen in CI, #865), the bus logs "Invalidation broadcast
failed", and other workers keep the stale value until its TTL.

In scope: make the command connection already open when a publish needs it, in the cases we
can see coming. Out of scope: any change to the 1 s budget, the bus's swallow-and-log
contract, or delivery guarantees. Invalidation stays best-effort over a TTL floor.

## Approach

**Chosen: warm from the listener.** Each time the listener task's SUBSCRIBE succeeds (first
boot, and every reconnect after an outage), it sends one `PING` on the command client, bounded
by `SUBSCRIBE_TIMEOUT_SECONDS`. That opens a pooled connection, which the next publish reuses.
`start()` still never waits on Redis.

Rejected:
- **A separate connect budget** (say 1 s connect + 1 s publish). It doubles the worst case a
  request can be held, and it still loses the message when the connect is slower than that.
- **Publish from a background sender queue with retry.** This takes publish out of the request
  path entirely. But it changes the transport contract (`publish` would no longer raise for
  the bus to log), queued messages are lost at shutdown, and it is more machinery than a
  best-effort accelerator needs.

## Design

In `modules/background_tasks/background_tasks/core/invalidation.py`, right after
`pubsub.subscribe(...)` succeeds in `_listen`:

```python
await self._warm_publish_connection()
```

```python
async def _warm_publish_connection(self) -> None:
    """Open the command connection a publish will use, off the request path."""
    try:
        async with asyncio.timeout(SUBSCRIBE_TIMEOUT_SECONDS):
            await self._client.ping()
    except Exception as exc:  # the listener stays up; a publish just connects cold
        logger.debug("Invalidation publish connection not warmed: %s", exc)
```

- A failed warm-up never fails or restarts the listener. The subscription is what keeps this
  worker receiving; the warm-up only saves the next publish a connect.
- Cancellation (`stop()`) still propagates, because `CancelledError` is not an `Exception`.
- The constants and docstrings say why: `PUBLISH_TIMEOUT_SECONDS` gains one sentence on the warm
  connection.

## Decisions made

- Warm on every successful subscribe, not only the first. A Redis restart drops both
  connections, and the listener notices it first (health check within ~15 s).
- Bound the PING by `SUBSCRIBE_TIMEOUT_SECONDS` (5 s), not the publish budget: it is not in a
  request's way.
- Failures log at DEBUG. The listener already warns once per outage, and a second warning for
  the same outage would be noise.
- No new setting or environment variable.
- The #881 test fixture that raises the publish timeout in the real-Redis tests stays. Those
  tests publish right after `start()`, before a warm-up can finish.

## Testing

New file `modules/background_tasks/tests/core/invalidation/test_background_tasks_invalidation_warmup.py`
(the existing files are at 276–293 of the 300-line cap):

- With the fake client: after the listener subscribes, the client receives one `ping`; after a
  scripted subscribe failure and a reconnect, it receives another.
- With the fake client: a `ping` that raises, or hangs (bounded by a patched short timeout),
  leaves the listener subscribed and delivering.
- With a real `redis-server`: once subscribed, the server reports a second client for this
  transport whose last command is `ping` (`CLIENT LIST`). A publish then reuses it, and the
  server's client count does not grow.

The fake gains an `async def ping()`. Full `make test-py` with `SM_TEST_REDIS_URL`, plus
`make lint`. No browser QA (`--skip-browser`): nothing user-visible changes.

## Risks

- redis-py might discard idle pool connections, so the warmed connection would not be reused.
  It doesn't (`ConnectionPool` keeps released connections until `disconnect`); the real-Redis
  test pins this.
- The health check on an idle command connection runs inside the next publish's budget, but
  that is a PING round trip on an open socket, not a connect.
