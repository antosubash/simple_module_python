# End-to-End Testing

Playwright-driven smoke tests live in [tests/e2e/](../tests/e2e/) — currently
just [`test_settings_ui.py`](../tests/e2e/test_settings_ui.py), which logs in,
navigates to `/settings/modules`, toggles a module setting, and verifies the
change hot-reloads into `app.state` without a server restart.

End-to-end tests are gated behind the `e2e` pytest marker (declared in
your app's `pyproject.toml`) and are **excluded from the default
`uv run pytest` invocation**. Run them explicitly via the marker.

## Prerequisites

One-time setup on the machine that will run the tests:

```bash
uv sync
uv run playwright install chromium
```

Then bring up the full stack (in a separate terminal, leave it running):

```bash
docker compose up -d postgres   # skip if you're on the default SQLite config
make migrate                    # apply Alembic migrations
make dev                        # FastAPI on :8000 + Vite on :5050
```

Create the first admin user (needed for e2e auth):

```bash
uv run sm-users create-admin --email admin@example.com --password admin
```

Or set `SM_USERS_BOOTSTRAP_EMAIL` / `SM_USERS_BOOTSTRAP_PASSWORD` in `.env`
before the first `make dev` run.

## Running

```bash
uv run pytest -m e2e tests/e2e
```

## Configuration

When you write e2e tests, read these environment variables (all optional):

| Variable       | Default                   | Notes                                                        |
| -------------- | ------------------------- | ------------------------------------------------------------ |
| `E2E_BASE_URL` | `http://localhost:8000`   | Where the FastAPI host is listening.                         |
| `E2E_USERNAME` | `admin@example.com`       | Email of the admin user created via `sm-users create-admin`. |
| `E2E_PASSWORD` | `admin`                   | Password of the above admin user.                            |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | `dev-verify-token-secret-change-me` | Must match the running server's value so locally-minted invite tokens are accepted. |

## Debugging

To see what the browser is doing, run headed with the Playwright trace
viewer:

```bash
uv run pytest -m e2e tests/e2e --headed --slowmo 250
```

Add `--tracing on` to capture a trace for post-mortem inspection via
`playwright show-trace`.
