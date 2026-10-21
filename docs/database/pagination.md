# Pagination

One helper clamps, counts and slices, so every list agrees on what `?page=0`
or a page past the end means.

```python
from simple_module_db import PageParams, paginate
from simple_module_hosting.pagination import page_params


# JSON API: page < 1 or per_page outside 1..200 is a 422.
@router.get("/", response_model=None)
async def list_orders(
    params: PageParams = Depends(page_params(default_per_page=50)),
    db: AsyncSession = Depends(get_db),
):
    page = await paginate(db, select(Order).order_by(Order.id), params)
    return page  # items, total, page, per_page, pages
```

- `PageParams(page, per_page)` lives in `simple_module_db` (no FastAPI import).
  It normalises on construction (`page >= 1`, `1 <= per_page <= 200`), so
  `.offset` is never negative. `simple_module_hosting.pagination` builds it from
  the query string: `page_params(n)` is strict (422), `lenient_page_params(n)` /
  `LenientPageParamsDep` clamp garbage instead, for Inertia views reached from
  bookmarked URLs.
- `paginate(session, stmt, params, scalars=True)` counts `stmt` as a subquery,
  so soft-delete and tenant filters apply to the count exactly as to the rows.
  `stmt` needs its own `ORDER BY`. A page past the end is clamped to the last
  page and the returned `page` is the one served. Pass `scalars=False` for
  multi-column selects (items are rows).
- Queries that cannot use `paginate` (a window-function total, a service that
  counts separately) still share `clamp_page(page, total, per_page)`,
  `total_pages(total, per_page)` and `PageParams.offset`.
- Frontend: `PaginationBar` from `@simple-module-py/ui/components/PaginationBar`
  takes `page`, `perPage`, `total`, `onPageChange` (the `Page` shape).
