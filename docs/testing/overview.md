# Testing overview

The framework expects three kinds of tests:

- **Unit tests** — pure functions, small service methods against `db_session`. `uv run pytest <path>`.
- **Integration tests** — endpoints via `client` / `authenticated_client`. Still `pytest`.
- **E2E tests** — Playwright-driven browser tests marked `e2e`, excluded from default runs.

The default `pytest` invocation pins `-m 'not e2e'` (your app's `pyproject.toml`), so a normal test run never touches the Playwright suite — run those explicitly via `uv run pytest -m e2e tests/e2e`.

## Quick reference

| Command | What it does |
|---|---|
| `uv run pytest` | Run every Python test (e2e excluded). |
| `uv run pytest path/to/test_file.py::test_name` | Single test. |
| `uv run pytest -k "create_order"` | All tests matching a name pattern. |
| `uv run pytest --lf` | Last failed only. |
| `uv run pytest -x` | Stop at first failure. |
| `uv run pytest -v -s` | Verbose + capture off (see `print`). |
| `uv run pytest -m e2e tests/e2e` | Playwright suite against `localhost:8000`. Requires `make dev` running. |
| `cd client_app && npx vitest run` | Run every JS test. |
| `cd client_app && npx vitest run <path>` | Single JS test file. |

## Async mode

The root `pyproject.toml` sets `asyncio_mode = "auto"`. Async tests don't need `@pytest.mark.asyncio` — any `async def test_*` is picked up automatically. You still need it on fixtures that are async generators.

## File layout

```text
conftest.py                    # root fixtures: app, db_session, client, authenticated_client
tests/
├── framework/                 # tests against framework/ packages
│   ├── core/
│   ├── db/
│   └── hosting/
├── modules/                   # tests that live at the root, cross-module
└── e2e/                       # Playwright tests (marked `e2e`)
modules/<name>/tests/          # per-module pytest tests
```

Any `conftest.py` under a subtree can add more fixtures; they cascade down but don't leak sideways. Keep module-specific fixtures in the module's `tests/conftest.py`.

## What good tests look like

- Exercise **behavior**, not implementation. A test that asserts `assert service._private_method_called_twice` is a red flag — rewrite to assert on the observable outcome.
- Use the **real** DB (SQLite in-memory via `db_session`). Mocking SQLAlchemy is almost always wrong.
- Avoid mocking your own code. Mock **external** boundaries (HTTP, SMTP, queue). For internal calls, instantiate the collaborator.
- Use **`authenticated_client`** for endpoint tests that need auth — don't reinvent the session cookie.

## Coverage expectations

There's no enforced coverage percentage, but:

- Every new endpoint gets at least one happy-path test.
- Every new service method with branching logic gets branch coverage.
- Bug fixes land with a regression test.
- Migration files don't need tests — but if the data-migration logic is non-trivial, extract the logic into a module-level function and test that.

## JS / TSX tests

Vitest + Testing Library, configured in `vitest.config.ts` and `vitest.setup.ts`. Tests live next to the source:

```text
modules/orders/orders/pages/__tests__/Browse.test.tsx
packages/ui/src/components/__tests__/Button.test.tsx
```

Run all: `npx vitest run`. Watch: `npx vitest`. Single file: `npx vitest run path/to/Browse.test.tsx`.

Use `@testing-library/react`'s `render` and query helpers:

```tsx
import { render, screen } from "@testing-library/react";
import Browse from "../Browse";

it("shows the empty state", () => {
  render(<Browse orders={[]} />);
  expect(screen.getByText(/no orders yet/i)).toBeInTheDocument();
});
```

For pages that depend on `useT` / `useAuth`, wrap in a mock provider from `packages/ui/src/test-utils.tsx`.

## Flaky-test checklist

Before marking a test flaky, check:

- **Time-dependent?** Use `freezegun` or inject a clock.
- **Order-dependent?** Run `pytest -p no:randomly` to disable reordering and see if the issue is real ordering coupling.
- **Async-order-dependent?** `await` everything that returns a coroutine, including `session.flush()` and `session.refresh()`.
- **Shared state?** Check for `scope="module"` fixtures that should be `scope="function"`.

## Next steps

- [Fixtures](/testing/fixtures) — the shared fixtures in `conftest.py` and how to extend them.
- [E2E tests](/e2e-testing) — the Playwright suite.
