# simple_module_test

Shared pytest fixtures and helpers for writing tests against [simple_module](https://github.com/antosubash/simple_module_python) apps and modules.

Fixtures are exposed via a `pytest11` entry point, so installing the package is enough — no `conftest.py` import needed.

The plugin ignores the invoking project's `.env` before collection, while exported
environment variables and temporary configuration-test files still work. Test imports
default to `importlib`, allowing repeated basenames. Add support directories to pytest's
`pythonpath` when using plain helper imports or `pytest_plugins`.

## Install

```bash
pip install simple_module_test
# or, if you already pulled in the framework:
pip install "simple_module_hosting[dev]"
```

## What it provides

All fixtures below are auto-registered via the `pytest11` entry point — installing the package is enough.

- `fake_event_bus` — a fresh recording `EventBus` per test that captures every `publish`/`publish_nowait` call.
- `build_test_app` — callable returning a minimal FastAPI app that loads exactly one module.
- `settings` — a ready-to-use `Settings` instance with an in-memory SQLite database and multi-tenancy enabled.
- `db_state`, `engine`, `db_session` — fresh `DatabaseState` per test; `db_session` also creates all module tables and stamps `alembic_version` at head so the boot-time migration check passes.
- `app` — a `create_app(settings)` instance with `lifespan` started and stopped.
- `client` — an `httpx.AsyncClient` bound to the test app.
- `authenticated_client` — same but with an admin user seeded and a forged session cookie attached. **Requires the `users` module** to be installed (it seeds the admin via `users.core.bootstrap`); apps scaffolded by `smpy` include it.
- `tenant_client` — factory: `async with tenant_client("member") as (client, tenant_id, user_id)` signs in a fresh user who is an `owner` / `admin` / `member` (default `owner`) of a new tenant — or of `tenant_id=` when given — with that tenant active. **Requires the `users` and `tenants` modules.**
- `oidc_test_issuer` — an in-process OpenID Connect issuer (`OidcTestIssuer`): an RSA signing key with `jwks()`, `discovery()` and `sign(claims)`, for testing an OIDC sign-in through `httpx_mock` without an IdP.

## Usage

In a module's `tests/test_something.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_create_order(authenticated_client):
    resp = await authenticated_client.post(
        "/api/orders",
        json={"customer_id": 1, "total_cents": 9900},
    )
    assert resp.status_code == 201
    assert resp.json()["total_cents"] == 9900
```

No fixture imports, no `conftest.py` — the `pytest11` entry point auto-loads them.

To enforce the standard package and test layout, call the public helper from a test:

```python
from pathlib import Path

from simple_module_test import assert_module_layout


def test_orders_layout():
    assert_module_layout(Path("modules/orders"), "orders")
```

For standalone module projects use `Path(".")`. Pass named domain directories with
`domain_areas={"fulfillment"}` and temporary compatibility files with `deprecated_root`.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`
- `pytest`, `pytest-asyncio`, `httpx`, `sqlalchemy`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
