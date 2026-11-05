# Fast pages

How to build an Inertia page that is fast, and that *feels* fast, in a
simple_module app. It covers the server (what a visit costs), the client
(bundle and render), the UX that decides how waiting feels, and how to measure
all three with the `simple-module-page-perf` skill.

## What "fast" means here

People notice three thresholds: about **100 ms** feels instant, about **1 s**
keeps their train of thought, and past **10 s** they leave. Google's Core Web
Vitals add two numbers for the first load: the largest element should paint
within **2.5 s** (LCP) and the page should not jump around after it does
(CLS ≤ **0.1**).

The page audit turns these into budgets. A value over the first number is a
warning; over the second, a failure:

| Budget | Warn | Fail | Measured as |
| --- | --- | --- | --- |
| Server time | 100 ms | 300 ms | `app` in the `Server-Timing` header, warm median |
| SQL statements | 12 | 25 | statements per visit, cheapest warm round |
| Page JSON | 100 KB | 300 KB | the Inertia response, without the i18n catalog |
| One prop | 50 KB | 150 KB | the largest page prop |
| Navigation | 300 ms | 1 s | click on a link → new page painted |
| Deferred props | 1 s | 2.5 s | click → every deferred prop painted |
| LCP (first load) | 2.5 s | 4 s | production build only |
| JS transferred | 350 KB | 600 KB | first load, production build only |
| CLS | 0.1 | 0.25 | first load and navigation |
| DOM nodes | 1,500 | 3,000 | after everything settled |
| Table rows | 100 | 250 | the longest `<tbody>` |

For scale, the framework's own pages on a production build (SQLite, one
worker, 2,000 users, 20,000 audit entries): server time 2–25 ms, 0–6 SQL
statements, client-side navigation 27–125 ms, LCP 144–328 ms, CLS 0.

## Where the time goes

A **first load** fetches the HTML document (with the page object inside it),
the shared bundle, the page's own chunk and its CSS, then renders. A
**client-side navigation** (any `<Link>` or `router.visit`) skips all of that:
one JSON request, the page chunk if it isn't cached yet, a React render.

```
click ─┬─ request ── server: auth, handler, queries, props, encode ─┐
       │                                                            │
       └──────────────── transfer (gzip) ── JSON parse ── chunk ── render ── paint
                                                                    │
                                     deferred props: one more request per group
```

So most of the work for a fast page is on the server, and most of the work for
a page that *feels* fast is deciding what can arrive later.

## Measure first

### `Server-Timing` in development

A development host adds a `Server-Timing` header to every response:

```
Server-Timing: app;dur=12.4, db;dur=3.1;desc="5 queries"
```

`app` is the time the request spent in the app (every middleware, the
handler, the commit). `db` is the time spent in the database driver, and
`desc` counts the SQL statements. Your browser's network panel shows both on
the request's *Timing* tab. The header is never sent outside development:
per-request timings help an attacker time lookups.

### The page audit

The `simple-module-page-perf` skill (`smpy skills add simple-module-page-perf`)
ships a script that signs in, finds every page from the menus, follows links
two levels deep (one sample per URL pattern, so a 50-row table adds one page),
and measures each page from the server, through a real browser, and at phone
width:

```bash
uv run --with playwright python .claude/skills/simple-module-page-perf/scripts/page_audit \
    --base-url http://localhost:8000 --email admin@example.com --password '…' \
    --json perf.json
```

Run it twice. Against a **development** server you get server time and SQL
counts, but dev-server bundle numbers are meaningless. Against a **production
build** (`make build`, then a non-development `SM_ENVIRONMENT`) you get LCP and
JS bytes, but no `Server-Timing`. The skill's `SKILL.md` has both recipes and
explains each finding.

### Pin it in a test

Once a page is fast, keep it that way. `track_queries()` counts the statements
a block runs on an engine instrumented with `install_query_stats()`. The test
that catches an N+1 compares a small table with a bigger one:

```python
from simple_module_db.query_stats import install_query_stats, track_queries


async def _statements(app, client) -> int:
    install_query_stats(app.state.sm.db.engine)
    counts = []
    # Auth adds statements on its own schedule (loading the principal, then a
    # session-version check), so the cheapest of three requests is the page's.
    for _ in range(3):
        with track_queries() as stats:
            resp = await client.get("/admin/orders/", headers={"X-Inertia": "true"})
        assert resp.status_code == 200
        counts.append(stats.count)
    return min(counts)


async def test_list_query_count_does_not_grow_with_rows(app, admin_client, db):
    await add_orders(db, 2)
    few = await _statements(app, admin_client)
    await add_orders(db, 20)
    assert await _statements(app, admin_client) == few
```

`modules/users/tests/test_users_admin_list_query_count.py` is a working copy.

## The server

### Send only what the page shows

Every byte of every prop is serialized, gzipped, sent, parsed and held in
memory by the client. Build a DTO with exactly the fields the page renders
rather than dumping a model, and keep large text (bodies, JSON blobs, audit
diffs) for the detail page.

### Paginate every list

A list that grows with the data is paginated on the server, 20–50 rows a
page. `paginate()` (`simple_module_db.pagination`) runs the count and the
page, and clamps a page past the end; `lenient_page_params()`
(`simple_module_hosting.pagination`) turns a hand-edited `?page=` into a
default instead of a 422; `PaginationBar` renders the control. For a feed the
user scrolls, use `scroll()` with Inertia's infinite scroll instead of pages.

### No query per row

The usual N+1: a list of N rows, then one more query per row for its roles,
owner or counts. Load relations in one query (`selectinload()` for
collections, `joinedload()` for a single parent), resolve users in one call
(`get_user_directory(app).get_many(ids)`), and compute per-row numbers with a
single `GROUP BY` instead of a `count()` per row. The `Server-Timing` count, or
the test above, tells you whether it worked.

### Pick the right kind of prop

`InertiaResponse` props can be plain values, callables, or wrapped with the
factories from `simple_module_inertia`:

| Prop | Sent on the first visit | On a partial reload | Use it for |
| --- | --- | --- | --- |
| `"rows": rows` | yes | only if named | cheap data, already computed |
| `"rows": load_rows` (a callable) | yes, evaluated | only if named, else **not evaluated** | anything the page reloads around |
| `optional(load)` | no | only if named | data a later interaction asks for |
| `always(value)` | yes | always, even when not named | things every reload must refresh |
| `defer(load, group=...)` | no: loaded right after the page renders | when named | slow parts of an otherwise fast page |
| `once(value)` | yes, then kept by the client | skipped while the client has it | large, rarely changing data (option lists) |
| `merge()` / `scroll()` | yes | appended to what the client has | infinite lists, "load more" |

Two rules follow:

- **Pass expensive props as callables.** A plain value is computed on every
  request, including a partial reload that leaves it out. A callable (sync or
  async, `lambda: service.stats()` is enough) is only evaluated when the
  response includes it.
- **Defer what is slow, not what is important.** The page should paint its
  structure and its main content at once; a deferred prop is for the part that
  depends on something slow (an external API, a broker, a big aggregate).
  Props in different `group=`s load in parallel; props in one group share a
  request.

The Background tasks *Workers* page is the worked example. Asking Celery which
workers are alive waits out a broker timeout, about one second. Before, the
whole page waited for it (server time about 1,050 ms). Now the snapshot is
deferred and everything else paints at once (about 20 ms):

```python
return await inertia.render(
    "BackgroundTasks/Workers",
    {
        # The routes and the start command render at once; the fleet fills
        # in behind a skeleton when the broker answers.
        "snapshot": defer(_snapshot_json(request), group="workers"),
        "queues": queues,
        "routes": routes,
    },
)
```

### Shared props are on every response

Everything a provider registered with `register_inertia_shared_provider()`
returns goes into every Inertia response (`docs/frontend/shared-props.md`).
Keep providers cheap, and return callables for anything that costs a query,
so a partial reload that does not name them skips them. The framework's own (`auth`, `menus`,
`i18n`) come to about 3 KB, and the translation catalog is sent once per tab:
the client echoes the catalog it holds in `X-SM-I18n`, so later visits come
back without it.

### Link to the canonical URL

A link to `/admin/orders` when the route is `/admin/orders/` costs a redirect:
one more round trip before anything paints. Menu URLs are checked for this
(`test_menu_urls_are_canonical.py`); links inside pages are not, so keep one
constant for the index URL with its trailing slash.

### Caching

Inertia responses are forced to `private, no-store`, so don't try to cache them
in the browser or a CDN. Cache *inside* the app instead: per-process caches
keyed on what they depend on, with a TTL, and `register_invalidations` to drop
them when the data changes (`docs/framework/invalidation.md`).

## The client

### Keep each page's JavaScript small

Each page is its own chunk (the `import.meta.glob` in the client app), so a
heavy library imported by one page only costs that page, *unless* it is
imported from a shared component. Load a heavy widget (a chart, an editor, a
map) where it is used:

```tsx
const Chart = lazy(() => import('./components/Chart'));

<Suspense fallback={<Skeleton className="h-64" />}>
  <Chart data={series} />
</Suspense>
```

`make build` prints chunk sizes; the audit reports JS transferred per first
load.

### Render less

- **Keep the DOM small.** Past about 1,500 nodes, every render and every style
  recalculation gets slower. Paginate, or virtualize a list that must show
  hundreds of rows.
- **Derive once.** Filtering or grouping a large prop on every render belongs
  in `useMemo`, keyed on the prop.
- **Stable keys.** Key list items by id, never by index, or React rebuilds
  rows it could have kept.

### Filters and search

A filter change is a visit to the same page with new query parameters. Reload
only what changes, keep the scroll position and the input's state, and don't
push a history entry per keystroke:

```tsx
router.get(INDEX_URL, params, {
  only: ['rows', 'pagination'],
  preserveState: true,
  preserveScroll: true,
  replace: true,
});
```

Debounce text inputs (about 300 ms) so typing a word costs one request, not
one per letter.

## UX: how waiting feels

Speed is measured in milliseconds, but judged by what the user sees while
waiting. These patterns matter as much as the numbers above.

### Show progress only when there is a wait

The client app shows Inertia's progress bar after 150 ms, so fast visits show
nothing and slow ones show that something is happening. Don't add a spinner of
your own for a whole-page visit.

### Placeholders keep the page still

A deferred prop or a lazy component needs a placeholder, and the placeholder
must take up the **same space** as what replaces it. Otherwise the content
below jumps when the data lands: that jump is layout shift, the CLS budget
above, and it makes people click the wrong thing.

- Use the `Skeleton` component (`@simple-module-py/ui/components/ui/skeleton`)
  in the shape of the real content: same grid, same card padding, same
  row heights.
- Or render the real component with "checking…" copy, the way the Background
  tasks list shows *Checking for workers…* in the same empty-state block that
  will hold the answer.
- Mark the placeholder `aria-busy="true"` (and `role="status"` with a label
  when it stands alone), so screen readers wait for the real content.
- Inertia's `<Deferred data="stats" fallback={…}>` does the bookkeeping for
  you. To handle it yourself, a deferred prop is `undefined` until it loads,
  which is different from `null` (loaded, nothing there). Type it as optional,
  `stats?: Stats`, and branch on `=== undefined`.
- A component that copies a deferred prop into state (`useState(initial)`)
  must adopt it when it arrives:
  `useEffect(() => { if (initial) setValue(initial); }, [initial]);`.

### Below the fold can wait

Content the user has to scroll to reach can load when it scrolls into view:
pass it as `optional()` and wrap it in
`<WhenVisible data="history" fallback={…}>`. The first response gets smaller
and nothing is fetched for users who never scroll.

### Distinct loading, empty and error states

"Loading", "there is nothing here", "your filter hides everything" and
"something is broken" need different messages, or a slow load reads as an
empty list and an outage reads as "no data". Give each its own copy, and give
the empty and error states a next step (clear the filter, start a worker).

### Buttons answer immediately

A submit button disables itself and shows progress while the request is in
flight (`form.processing` from `useForm`), so a slow save is never clicked
twice. On a validation error the server redirects back with the errors
(`docs/frontend/inertia.md`), and a `useForm` form still holds what the user
typed, so they fix one field instead of retyping the form.

### Polling and freshness

A page showing live state either polls or says how old it is.

- To poll, use `usePoll(interval, { only: [...] })` with a modest interval
  (5 s or more) and only the props that change. Inertia slows polling down
  while the tab is in the background.
- For anything that costs the server real work, prefer a manual *Refresh*
  button and a visible "last updated" time that turns amber when it goes
  stale. That is what the Workers page does.

### Prefetching: only where data can be a little old

`<Link prefetch>` fetches a page when the pointer rests on the link, so the
click feels instant. The response is cached briefly (`cacheFor`), so the click
can show data that is a few seconds old. That suits documentation and
reference pages. It does not suit admin lists right after an edit, or anything
whose GET has a cost. Every hover is a request.

### Phones

Check every page at phone width: nothing should scroll sideways (wrap wide
tables in `overflow-x-auto`), and touch targets should be at least 44 px tall
(`max-lg:min-h-11` on buttons). The audit loads every page at 390 px and
reports horizontal overflow.

### Small things that read as quality

One `<h1>` per page, an accessible name on every icon-only button, a document
title per page (`<Head title>`). The audit checks all three. They cost
nothing and make the page faster to *understand*, which is what the user
perceives.

## Checklist

Before calling a page done:

- [ ] Server time under 100 ms in development; anything slow is `defer()`ed
      with a same-size placeholder.
- [ ] The SQL count doesn't grow with the rows; a test pins it.
- [ ] Lists are paginated; no prop over 50 KB.
- [ ] Expensive props are callables, so partial reloads skip them.
- [ ] Filters reload with `only`, `preserveState`, `preserveScroll` and `replace`.
- [ ] No layout shift when deferred content lands (CLS ≤ 0.1).
- [ ] Loading, empty, filtered-empty and error states each have their own copy.
- [ ] Buttons disable while their request is in flight.
- [ ] Nothing scrolls sideways at 390 px.
- [ ] Links point at canonical URLs (no redirects).
- [ ] The page audit is clean on a development server and on a production build.
