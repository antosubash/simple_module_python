# End-to-End Testing

Playwright-driven smoke tests live in [tests/e2e/](../tests/e2e/) — currently
[`test_settings_ui.py`](../tests/e2e/test_settings_ui.py) (logs in, navigates to
`/admin/settings/`, toggles a module setting, and verifies the change
hot-reloads into `app.state` without a server restart) and
[`test_audit_log_ui.py`](../tests/e2e/test_audit_log_ui.py).

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
make docker-up                  # shared dev-services stack (Postgres/Redis/MinIO); skip if on default SQLite
make migrate                    # apply Alembic migrations
make dev                        # FastAPI on :8000 + Vite on :5050
```

Create the first admin user (needed for e2e auth):

```bash
uv run smpy users create-admin --email admin@example.com --password admin
```

Or set `SM_USERS_BOOTSTRAP_EMAIL` / `SM_USERS_BOOTSTRAP_PASSWORD` in `.env`
before the first `make dev` run.

## Running

```bash
uv run pytest -m e2e tests/e2e
```

## Inertia v3 fixture pages

The framework's own pages never use partial reloads, deferred, merge or `once`
props, infinite scroll, error bags, history encryption, `WhenVisible`, polling
or prefetch. The dev host therefore ships fixture pages that do, so
`tests/e2e/test_inertia_*.py` can drive those client features in a real
browser:

- Routes: [`host/e2e_inertia/`](../host/e2e_inertia/) under
  `/__e2e/inertia/*`, plus loader counters at `GET /__e2e/inertia/_probes`
  (reset with `POST /__e2e/inertia/_probes/reset`).
- Pages: `host/client_app/pages/E2eInertia/*.tsx`, rendered as
  `E2eInertia/<Page>`. They are marked `i18n-exempt-file` and never shown to
  users.
- Gating: `host/main.py` mounts the router only when `SM_ENVIRONMENT` is
  `development`, and every route needs a signed-in user. In any other
  environment the paths do not exist (`host/tests/test_e2e_inertia_gating.py`).
- Fixtures: `tests/e2e/inertia_support.py` signs in once per session through
  the API and fails a test on any console or page error. Mark a test
  `allow_resource_errors` when it provokes a 4xx/5xx on purpose.

Run them against a development server (Vite required, as for every e2e test):

```bash
uv run pytest -m e2e tests/e2e/test_inertia_*.py
```

## Configuration

When you write e2e tests, read these environment variables (all optional):

| Variable       | Default                   | Notes                                                        |
| -------------- | ------------------------- | ------------------------------------------------------------ |
| `E2E_BASE_URL` | `http://localhost:8000`   | Where the FastAPI host is listening.                         |
| `E2E_USERNAME` | `admin@example.com`       | Email of the admin user created via `smpy users create-admin`. |
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
