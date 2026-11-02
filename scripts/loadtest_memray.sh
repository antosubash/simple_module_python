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

# Refuse an occupied port before seeding or driving an unrelated server.
python3 - "$PORT" <<'PY'
import socket
import sys

with socket.socket() as sock:
    # Match uvicorn: leftover TIME_WAIT from a previous run is not "occupied".
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", int(sys.argv[1])))
PY
command -v setsid > /dev/null

# Default locust scenario — override by passing any locust flags as arguments.
if [ "$#" -eq 0 ]; then
  set -- -u 20 -r 5 -t 30s
fi

mkdir -p "$(dirname "$PROFILE")"

# Seed the load-test admin and export the signed session cookie so the
# locustfile's AuthedUser activates. Skip with SKIP_SEED=1.
if [ "${SKIP_SEED:-0}" != "1" ]; then
  echo "[loadtest-memray] seeding load-test user"
  eval "$(uv run python scripts/loadtest_seed.py)"
  export SM_LOADTEST_COOKIE
fi

echo "[loadtest-memray] starting uvicorn under memray → $PROFILE"
# --force overwrites any previous profile; --follow-fork picks up any children
# uvicorn might spawn (none in single-worker mode, but harmless).
setsid uv run memray run --force --follow-fork -o "$PROFILE" \
  -m uvicorn host.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!

# setsid gives the wrapper and its descendants a process group owned by this run.
_signal_tree() {
  local sig=$1
  kill "-$sig" -- "-$SERVER_PID" 2>/dev/null || true
}

cleanup() {
  if kill -0 -- "-$SERVER_PID" 2>/dev/null; then
    echo "[loadtest-memray] stopping uvicorn (pid $SERVER_PID)"
    _signal_tree INT
    # Give memray a moment to flush the profile; escalate if it lingers.
    for _ in $(seq 1 20); do
      kill -0 -- "-$SERVER_PID" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 -- "-$SERVER_PID" 2>/dev/null; then
      _signal_tree TERM
      for _ in $(seq 1 20); do
        kill -0 -- "-$SERVER_PID" 2>/dev/null || break
        sleep 0.25
      done
      _signal_tree KILL
    fi
  fi
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Wait for /health/live — fail loudly if the server doesn't come up.
echo "[loadtest-memray] waiting for $HOST/health/live"
for _ in $(seq 1 60); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[loadtest-memray] server exited before becoming healthy" >&2
    exit 1
  fi
  if curl -sf --max-time 2 "$HOST/health/live" > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -sf --max-time 2 "$HOST/health/live" > /dev/null 2>&1; then
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
