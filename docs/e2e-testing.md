# End-to-End Testing

The repo ships Playwright-driven smoke tests at
[tests/e2e/test_smoke.py](../tests/e2e/test_smoke.py). Four tests drive a real
Chromium browser through the core flows:

* **`test_login_and_browse_smoke`** — landing → local email+password login →
  dashboard → products browse → logout. Minimal regression guard.
* **`test_products_crud_smoke`** — same login + a full create / edit / delete
  round-trip against the products module.
* **`test_password_reset_smoke`** — **skipped** (see inline comment in the
  test file).  `fastapi-users` `reset_password()` validates a password
  fingerprint (`password_fgpt`) that is only available server-side.  The
  full HTTP-layer flow is covered by unit tests in
  `modules/users/tests/test_api_auth.py`.
* **`test_admin_invite_smoke`** — admin invites a new user via the UI; the
  invitee accepts the invite in a fresh browser context and lands on the
  dashboard.  Token is minted locally using the dev-default verify secret
  (equivalent to what the ConsoleMailer logs).

End-to-end tests are gated behind the `e2e` pytest marker (declared in
[pyproject.toml](../pyproject.toml)) and are **excluded from the default
`make test` run**. They only execute under `make test-e2e`.

## Prerequisites

One-time setup on the machine that will run the tests:

```bash
uv sync --all-packages
uv run playwright install chromium
```

Then bring up the full stack (in a separate terminal, leave it running):

```bash
make docker-up     # Postgres (skip if using the default SQLite config)
make migrate       # apply Alembic migrations
make dev           # FastAPI on :8000 + Vite on :5173
```

Create the first admin user (needed for e2e auth):

```bash
uv run sm users create-admin --email admin@example.com --password admin
```

Or set `SM_USERS_BOOTSTRAP_EMAIL` / `SM_USERS_BOOTSTRAP_PASSWORD` in `.env`
before the first `make dev` run.

## Running

```bash
make test-e2e
```

Or directly:

```bash
uv run pytest -m e2e tests/e2e
```

## Configuration

The tests read these environment variables (all optional):

| Variable       | Default                   | Notes                                                        |
| -------------- | ------------------------- | ------------------------------------------------------------ |
| `E2E_BASE_URL` | `http://localhost:8000`   | Where the FastAPI host is listening.                         |
| `E2E_USERNAME` | `admin@example.com`       | Email of the admin user created via `sm users create-admin`. |
| `E2E_PASSWORD` | `admin`                   | Password of the above admin user.                            |
| `SM_USERS_VERIFICATION_TOKEN_SECRET` | `dev-verify-token-secret-change-me` | Must match the running server's value so locally-minted invite tokens are accepted. |

## What the smoke tests cover

**`test_login_and_browse_smoke`**

1. Landing page renders (`/`) with the "Get Started" CTA.
2. Local email+password login via `/users/login`.
3. Dashboard (`/dashboard/`) renders — proves session cookie + AuthMiddleware +
   Inertia resolver + AuthenticatedLayout.
4. Products browse (`/products/`) renders — proves module pages resolve.
5. Logout returns the user to the public landing page.

**`test_products_crud_smoke`**

1. Login as admin.
2. Create a timestamped product via the Create form.
3. Edit its name and verify the new name appears in the list.
4. Delete it through the confirm dialog and verify the row disappears.

The CRUD test relies on the admin user having the `admin` role (created
automatically by `sm users create-admin` or the bootstrap env vars).

**`test_admin_invite_smoke`**

1. Admin logs in and submits the invite form at `/users/admin/invite`.
2. The test looks up the new user's UUID via the admin API.
3. A verify token is minted locally (same secret the server uses).
4. A fresh browser context navigates to `/users/invite/accept?token=…`, sets
   a password, and verifies a redirect to `/dashboard`.

These are **not** pixel-perfect regression tests — the goal is to catch broad
breakage in the auth + render + CRUD spine.

## Debugging

To see what the browser is doing, run headed with the Playwright trace
viewer:

```bash
uv run pytest -m e2e tests/e2e --headed --slowmo 250
```

Add `--tracing on` to capture a trace for post-mortem inspection via
`playwright show-trace`.
