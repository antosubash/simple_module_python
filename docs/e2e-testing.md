# End-to-End Testing

The repo ships Playwright-driven smoke tests at
[tests/e2e/test_smoke.py](../tests/e2e/test_smoke.py). Two tests drive a real
Chromium browser through the core flows:

* **`test_login_and_browse_smoke`** — landing → Keycloak login → dashboard →
  products browse → logout. Minimal regression guard.
* **`test_products_crud_smoke`** — same login + a full create / edit / delete
  round-trip against the products module.

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
make docker-up     # Keycloak + Postgres
make migrate       # apply Alembic migrations
make dev           # FastAPI on :8000 + Vite on :5173
```

## Running

```bash
make test-e2e
```

Or directly:

```bash
uv run pytest -m e2e tests/e2e
```

## Configuration

The test reads three environment variables (all optional):

| Variable       | Default                   | Notes                                                              |
| -------------- | ------------------------- | ------------------------------------------------------------------ |
| `E2E_BASE_URL` | `http://localhost:8000`   | Where the FastAPI host is listening.                               |
| `E2E_USERNAME` | `admin`                   | Keycloak username. The seeded `admin` user has role `admin`.       |
| `E2E_PASSWORD` | `admin`                   | Keycloak password for the above user.                              |

Seeded Keycloak users live in [keycloak/realm-export.json](../keycloak/realm-export.json).
The defaults match the `admin`/`admin` user out of the box.

## What the smoke tests cover

**`test_login_and_browse_smoke`**

1. Landing page renders (`/`) with the "Get Started" CTA.
2. Keycloak OIDC login round-trip.
3. Dashboard (`/dashboard/`) renders — proves session cookie + AuthMiddleware +
   Inertia resolver + AuthenticatedLayout.
4. Products browse (`/products/`) renders — proves module pages resolve.
5. Logout returns the user to the public landing page.

**`test_products_crud_smoke`**

1. Login as admin.
2. Create a timestamped product via the Create form.
3. Edit its name and verify the new name appears in the list.
4. Delete it through the confirm dialog and verify the row disappears.

The CRUD test relies on the Keycloak `simple-module-app` client shipping a
`realm roles` protocol mapper that emits `realm_access.roles` into userinfo
(see [keycloak/realm-export.json](../keycloak/realm-export.json)); without
that, `RequiresPermission("products.create")` returns 403.

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
