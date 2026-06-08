# Fixtures

The `simple_module_test` plugin provides app-level fixtures that every test directory inherits — auto-loaded via its `pytest11` entry point, so installing the package is enough (no `conftest.py` import needed). Everything you need for a typical integration test — app, DB session, HTTP client, authenticated client — is already wired up.

## Available fixtures

| Fixture | Scope | Returns | Use when |
|---|---|---|---|
| `settings` | function | `Settings` | You need to read the in-memory test settings (SQLite, `multi_tenant=True`). |
| `db_state` | function | `DatabaseState` | Low-level access to engines / sessions outside a request. |
| `engine` | function | `AsyncEngine` | You need the raw async engine (rare). |
| `db_session` | function | `AsyncSession` | Unit-testing a service. Tables created, Alembic head stamped. |
| `app` | function | `FastAPI` | Endpoint tests that don't need an HTTP client. |
| `client` | function | `httpx.AsyncClient` | Anonymous HTTP calls to the app. |
| `authenticated_client` | function | `httpx.AsyncClient` | Admin-scoped HTTP calls — carries a signed session cookie. |

All fixtures are **function-scoped** — each test gets its own. The SQLite database is in-memory; tearing down and re-creating is cheap.

## `settings`

A pre-built `Settings` object using the in-memory SQLite URL and `multi_tenant=True`. Most tests don't use it directly — the `app` fixture consumes it.

```python
def test_settings_defaults(settings):
    assert settings.multi_tenant is True
    assert settings.database_url.startswith("sqlite")
```

## `db_session`

The workhorse. Creates a fresh in-memory DB, runs `CREATE TABLE` for every module's tables (iterating `all_module_bases` and calling `base.metadata.create_all`), stamps `alembic_version` at head, and yields an `AsyncSession`.

```python
from decimal import Decimal
from orders.models import Order

@pytest.mark.asyncio
async def test_create_order(db_session):
    order = Order(customer_email="a@b.c", total=Decimal("1"))
    db_session.add(order)
    await db_session.flush()
    assert order.id is not None
```

Notes:

- **Tables are created directly from model metadata** (not `alembic upgrade`). This keeps tests fast. Alembic migrations are exercised separately — see [Migrations § Testing](/database/migrations).
- Stamping `alembic_version` at head means the boot-time migration check in the `app` fixture passes. If you change this, expect `SM010` to fail every test.
- Each test gets a fresh DB — no transaction-rollback trickery.

## `app`

Calls `create_app(settings)` and starts the lifespan. All modules are discovered, middleware is installed, `register_*` hooks run. Returns the `FastAPI` instance with a started lifespan; the fixture teardown closes it.

Useful for tests that exercise framework registrations:

```python
@pytest.mark.asyncio
async def test_menu_registered(app):
    menus = app.state.sm.menu_registry
    assert any(m.key == "orders" for m in menus.items())
```

## `client`

An `httpx.AsyncClient` pointed at the `app` via `ASGITransport`. No auth cookie.

```python
@pytest.mark.asyncio
async def test_landing_page(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "Welcome" in r.text
```

For endpoints that return JSON:

```python
r = await client.get("/api/orders")
assert r.json() == []
```

401 / 403 are expected for authenticated endpoints — use `authenticated_client` instead.

## `authenticated_client`

Same as `client`, but the fixture also:

1. Seeds an admin user via `users.bootstrap.create_admin(...)`.
2. Forges a signed session cookie for that user.
3. Attaches the cookie to the client.

> Because it seeds via `users.bootstrap`, this fixture requires the `users` module to be installed (the import is deferred to the fixture body, so the rest of the plugin loads without it). Apps scaffolded by `smpy` include `users`.

```python
@pytest.mark.asyncio
async def test_create_order_as_admin(authenticated_client):
    r = await authenticated_client.post(
        "/api/orders",
        json={"customer_email": "a@b.c", "total": "1.00"},
    )
    assert r.status_code == 201
```

The admin has `*` permission (via `DEFAULT_ROLE_PERMISSIONS["admin"]`), so it bypasses every `RequiresPermission` check. For tests that require a less-privileged principal, create a separate user and sign in via the login endpoint:

```python
@pytest.mark.asyncio
async def test_non_admin_denied(client, db_session):
    from users.admin.service import UserService
    svc = UserService(db_session)
    await svc.create(email="u@e.com", password="x", roles=["viewer"])
    await db_session.commit()

    login = await client.post(
        "/users/login", data={"email": "u@e.com", "password": "x"}
    )
    assert login.status_code in (200, 303)

    r = await client.post("/api/orders", json={...})
    assert r.status_code == 403
```

## Fixture composition

Fixtures compose the expected way — `client` and `authenticated_client` depend on `app`, which depends on `settings` (and creates its own tables on `app.state.sm.db.engine`). The `db_session` / `engine` fixtures depend on `db_state`, which builds its own in-memory engine independent of `settings`. Request only the fixture you need; the DAG pulls in the rest.

Adding your own fixtures at module level:

```python
# modules/orders/tests/conftest.py
import pytest
from orders.service import OrderService

@pytest.fixture
def order_service(db_session):
    return OrderService(db_session)
```

Now every test in `modules/orders/tests/` can take `order_service` as a parameter.

## Overriding dependencies

FastAPI dependency overrides work as usual:

```python
@pytest.mark.asyncio
async def test_with_mock_mailer(app, authenticated_client):
    from users.deps import _mailer
    captured = []
    def fake_mailer():
        return type("Mailer", (), {"send": lambda *a: captured.append(a)})()
    app.dependency_overrides[_mailer] = fake_mailer

    await authenticated_client.post(
        "/users/admin/invite", data={"email": "x@y.z"}
    )
    assert len(captured) == 1
```

Overrides applied to `app` persist for the lifetime of the fixture — no need to clean up; the next test gets a fresh `app`.

## Time-sensitive tests

Use `freezegun`:

```python
from freezegun import freeze_time

@pytest.mark.asyncio
async def test_order_timestamps(db_session):
    with freeze_time("2026-01-01T12:00:00Z"):
        order = Order(customer_email="a@b.c", total=Decimal("1"))
        db_session.add(order)
        await db_session.flush()
        assert order.created_at.isoformat().startswith("2026-01-01T12:00:00")
```

Don't rely on `datetime.now()` assertions with tolerance windows — they're flaky and slower to read.

## Mocking external services

For HTTP, SMTP, storage backends — mock at the boundary with `httpx_mock`, `aiosmtpd`, or a service-registered fake. **Don't** monkeypatch the module you're testing; its behavior is what's under test.

Example with `httpx_mock`:

```python
@pytest.mark.asyncio
async def test_webhook_delivery(httpx_mock, db_session):
    httpx_mock.add_response(url="https://example.com/hook", status_code=200)
    await deliver_webhook(db_session, "https://example.com/hook", {"id": 1})
    assert httpx_mock.get_request().content == b'{"id": 1}'
```

## Parametrization

Standard pytest:

```python
@pytest.mark.parametrize("status,expected", [
    ("pending", 200),
    ("shipped", 200),
    ("invalid", 422),
])
@pytest.mark.asyncio
async def test_status_transitions(authenticated_client, status, expected):
    r = await authenticated_client.patch(
        "/api/orders/1", json={"status": status}
    )
    assert r.status_code == expected
```
