# simple_module_test

Shared pytest fixtures and helpers for writing tests against [simple_module](https://github.com/antosubash/simple_module_python) apps and modules.

Fixtures are exposed via a `pytest11` entry point, so installing the package is enough — no `conftest.py` import needed.

## Install

```bash
pip install simple_module_test
# or, if you already pulled in the framework:
pip install "simple_module_hosting[dev]"
```

## What it provides

- `settings` — a ready-to-use `Settings` instance with an in-memory SQLite database and multi-tenancy enabled.
- `db_state`, `engine`, `db_session` — fresh `DatabaseState` per test; `db_session` also creates all module tables and stamps `alembic_version` at head so the boot-time migration check passes.
- `app` — a `create_app(settings)` instance with `lifespan` started and stopped.
- `client` — an `httpx.AsyncClient` bound to the test app.
- `authenticated_client` — same but with an admin user seeded and a forged session cookie attached.

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

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`
- `pytest`, `pytest-asyncio`, `httpx`, `sqlalchemy`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
