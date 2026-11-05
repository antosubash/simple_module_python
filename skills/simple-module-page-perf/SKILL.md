---
name: simple-module-page-perf
description: Use when checking or improving the speed and perceived speed of Inertia pages in a simple_module_python app — a page or navigation feels slow, a list may have an N+1, a payload looks large, content jumps while loading, or before shipping a new page. Triggers on "page is slow", "audit page performance", "Server-Timing", "N+1", "defer this prop", "layout shift", "skeleton", "LCP", or "perf check the pages".
---

# simple_module_python: page performance audit

`scripts/page_audit` (next to this file) signs in to a running app, finds every
page, and measures each one three ways: the Inertia JSON a navigation fetches,
a real browser load and click-through, and a phone-width load. It prints a
Markdown table and a findings list, and exits 1 if any budget fails.

## 1. Run it against a development server (server-side numbers)

A development host sends `Server-Timing: app;dur=…, db;dur=…;desc="N queries"`
on every response. The audit reads it to report server time and SQL
statements per page.

```bash
uv run --with playwright playwright install chromium   # once
uv run --with playwright python .claude/skills/simple-module-page-perf/scripts/page_audit \
    --base-url http://localhost:8000 \
    --email admin@example.com --password '<admin password>' \
    --json perf-dev.json
```

- Pages come from the `menus` shared prop, then two levels of links found in
  each page's `<main>`, one sample per URL pattern (`/orders/<id>` is audited
  once). Add pages with `--path /x/` (repeatable), audit only those with
  `--no-discover --crawl-depth 0`.
- Logout, delete, export, download, `/api/` and `/setup` links are never
  followed. Add your own with `--exclude <regex>`.
- Public pages: run without `--email` and pass them with `--path`
  (`--path / --path /users/login`).
- No `Server-Timing` (older framework, or a non-development server): the
  Server ms and SQL columns show `—`; everything else still works.
- Seed realistic volumes first. Ten rows hide the N+1 and the oversized prop
  that ten thousand expose.

## 2. Run it against a production build (what users download)

Dev-server bundles are unminified and served module by module, so LCP and JS
bytes only mean something on a build. The audit only applies those budgets
when the page is not served by Vite.

```bash
make build                                # the client bundle
SM_ENVIRONMENT=staging SM_SECRET_KEY=<32+ chars> <the other secrets production needs> \
    uv run uvicorn main:app --port 8001   # any non-development environment serves the build
uv run --with playwright python .claude/skills/simple-module-page-perf/scripts/page_audit \
    --base-url http://localhost:8001 --email … --password … --json perf-prod.json
```

Outside development the session cookie is `Secure`. Browsers accept it on
`http://localhost`; over plain HTTP on any other host, set
`SM_SESSION_COOKIE_SECURE=false` for the audit run.

## 3. Read the report

| Column / check | Budget (warn / fail) | What it means |
| --- | --- | --- |
| Server ms | 100 / 300 | warm median of `app` in Server-Timing |
| SQL | 12 / 25 | statements, cheapest warm round (auth adds a few now and then) |
| JSON KB | 100 / 300 | the Inertia response without the i18n catalog |
| `prop_kb` | 50 / 150 | the largest single page prop |
| Deferred | — | props the page loads after it paints |
| Nav ms | 300 / 1000 | click on a visible link → new page painted (`—`: no visible link to it) |
| `deferred_ms` | 1000 / 2500 | click → every deferred prop painted |
| LCP ms | 2500 / 4000 | production build only |
| `js_kb` | 350 / 600 | JS transferred on first load, production build only |
| CLS | 0.1 / 0.25 | layout shift on first load or navigation |
| DOM / `table_rows` | 1500 / 3000, 100 / 250 | rendered size after everything settled |
| `redirect` | warn | the GET redirected: link to the canonical URL |
| `console`, `failed_requests` | fail | runtime errors, 4xx/5xx requests while on the page |
| `overflow` | warn | page scrolls sideways at 390 px |
| `stuck_loaders` | warn | skeleton/spinner/`aria-busy` still visible after everything settled |
| `unnamed_controls`, `h1` | warn | icon buttons without a name; not exactly one `<h1>` |

Override a budget with `--budget queries=20,40`. Use `--no-fail` to report
without failing.

## 4. Fix what it finds

| Finding | Usual cause | Fix |
| --- | --- | --- |
| High SQL count | a query per row (N+1) | `selectinload()`/`joinedload()`, `get_user_directory(app).get_many(ids)`, one `GROUP BY` for per-row counts |
| High server ms, few queries | a slow call: broker, HTTP API, big aggregate | `defer(load, group="…")` with a same-size placeholder, or cache with a TTL plus invalidation |
| Large JSON / prop | whole models, unpaginated lists | a DTO with only the rendered fields; `paginate()` 20–50 rows; detail data on the detail page |
| Partial reloads still slow | props passed as values, so computed every time | pass expensive props as callables (`"stats": lambda: svc.stats()`): only evaluated when included |
| `deferred_ms` warning | the deferred work itself is slow | fine if the placeholder says what is loading; split independent slow props into separate groups (parallel requests) |
| CLS | content appears without reserved space | `Skeleton` in the real layout's shape; same component with "checking…" copy; `aria-busy="true"` |
| `redirect` | a link without the trailing slash, or to an old URL | one constant for the index URL, with its slash |
| `js_kb` | heavy library in a shared component | `lazy(() => import('./Heavy'))` + `<Suspense fallback={<Skeleton …/>}>` where it is used |
| DOM / rows | long unpaginated list | paginate, or virtualize past a few hundred rows |
| `overflow` | wide table or fixed widths | `overflow-x-auto` around tables; no fixed pixel widths |

How deferred props behave on the client:

- A deferred prop is `undefined` until it loads, which is different from `null`
  (loaded, nothing there). Type it optional (`stats?: Stats`) and branch on
  `=== undefined`, or wrap the part in Inertia's
  `<Deferred data="stats" fallback={…}>`.
- A component that copies the prop into state must adopt it when it arrives:
  `useEffect(() => { if (initial) setValue(initial); }, [initial]);`.
- Test the server side with `InertiaPage` from `simple_module_test`:
  `page.deferred("group", "prop").missing("prop")`, then
  `await page.load_deferred(client, "group")`.

## 5. Pin it

Keep a fixed page fixed with a statement-count test. The cheapest of three
requests excludes the auth layer's own periodic queries:

```python
from simple_module_db.query_stats import install_query_stats, track_queries


async def _statements(app, client, url) -> int:
    install_query_stats(app.state.sm.db.engine)
    counts = []
    for _ in range(3):
        with track_queries() as stats:
            assert (await client.get(url, headers={"X-Inertia": "true"})).status_code == 200
        counts.append(stats.count)
    return min(counts)


# Seed 2 rows, measure; seed 20 more, measure again; assert the counts are equal.
```

## UX checklist the numbers don't cover

Walk through these by hand on each page you touched:

- A visit under about 150 ms shows nothing; Inertia's progress bar covers longer
  ones. Don't add page-level spinners.
- Loading, empty, filtered-empty and error states each say something different
  and offer a next step.
- Submit buttons disable while `form.processing` is true; validation errors keep
  what the user typed.
- Filters reload with `only`, `preserveState`, `preserveScroll` and
  `replace: true`; text inputs are debounced (about 300 ms).
- Live data either polls modestly (`usePoll(5000+, { only })`) or shows
  "last updated" next to a Refresh button.
- `<Link prefetch>` only where slightly stale data is fine; every hover is a request.
- Touch targets are at least 44 px tall on phones (`max-lg:min-h-11`).

## Gotchas

- Run the audit against a server that nothing else is changing: a Vite HMR
  reload in the middle of a run shows up as layout shift and console errors.
- `Nav ms` needs a visible link to the page from its parent, a sibling page in
  the same area, or home. Pages only reachable from a dropdown show `—`.
- A `fail` on a crawled detail page with HTTP 404 or 422 is usually seed data
  linking to rows that don't exist. Check the link before chasing it.
- The browser pass drives one tab; don't run two audits against one server
  at the same time, or the timings measure each other.
