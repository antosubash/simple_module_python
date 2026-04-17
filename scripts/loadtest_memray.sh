#!/usr/bin/env bash
# Start uvicorn wrapped in memray, drive it with locust, then emit a flamegraph.
#
# memray instruments the parent python process, so we run uvicorn with a single
# worker and no --reload (reload spawns subprocesses memray cannot see).
#
# Usage: scripts/loadtest_memray.sh [locust-args...]
#   Defaults: -u 20 -r 5 -t 30s
#   Override: scripts/loadtest_memray.sh -u 50 -r 10 -t 60s
set -euo pipefail

HOST=${HOST:-http://localhost:8000}
PORT=${PORT:-8000}
PROFILE=${PROFILE:-.memray/loadtest.bin}
LOCUSTFILE=${LOCUSTFILE:-tests/loadtest/locustfile.py}

# Default locust scenario — override by passing any locust flags as arguments.
if [ "$#" -eq 0 ]; then
  set -- -u 20 -r 5 -t 30s
fi

mkdir -p "$(dirname "$PROFILE")"

# Seed the load-test admin and export the signed session cookie + CSRF token
# so the locustfile's AuthedUser activates. Skip with SKIP_SEED=1.
if [ "${SKIP_SEED:-0}" != "1" ]; then
  echo "[loadtest-memray] seeding load-test user"
  eval "$(uv run python scripts/loadtest_seed.py)"
  export SM_LOADTEST_COOKIE SM_LOADTEST_CSRF
fi

echo "[loadtest-memray] starting uvicorn under memray → $PROFILE"
# --force overwrites any previous profile; --follow-fork picks up any children
# uvicorn might spawn (none in single-worker mode, but harmless).
uv run memray run --force --follow-fork -o "$PROFILE" \
  -m uvicorn host.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!

# Signal the memray wrapper AND any descendants. uv + memray spawn uvicorn as
# a grandchild, so signaling just $SERVER_PID leaves uvicorn attached to the
# port. `pkill -P` walks one level of children; we also hit whatever is bound
# to the port as a belt-and-braces final check.
_signal_tree() {
  local sig=$1
  kill "-$sig" "$SERVER_PID" 2>/dev/null || true
  pkill "-$sig" -P "$SERVER_PID" 2>/dev/null || true
}

cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[loadtest-memray] stopping uvicorn (pid $SERVER_PID)"
    _signal_tree INT
    # Give memray a moment to flush the profile; escalate if it lingers.
    for _ in $(seq 1 20); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      _signal_tree TERM
      wait "$SERVER_PID" 2>/dev/null || true
    fi
  fi
  # Last-ditch: anything still bound to the port is ours to reap.
  if command -v lsof > /dev/null 2>&1; then
    lsof -ti tcp:"$PORT" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Wait for /health/live — fail loudly if the server doesn't come up.
echo "[loadtest-memray] waiting for $HOST/health/live"
for _ in $(seq 1 60); do
  if curl -sf "$HOST/health/live" > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -sf "$HOST/health/live" > /dev/null 2>&1; then
  echo "[loadtest-memray] server did not become healthy in 30s" >&2
  exit 1
fi

echo "[loadtest-memray] running locust: $*"
uv run locust -f "$LOCUSTFILE" --headless --host "$HOST" "$@"

cleanup
trap - EXIT INT TERM

echo "[loadtest-memray] rendering flamegraph"
uv run memray flamegraph --force "$PROFILE"
echo "[loadtest-memray] done — open .memray/memray-flamegraph-loadtest.html"
