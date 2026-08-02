# simple_module_catalog

A sample product catalog for [simple_module](https://github.com/antosubash/simple_module_python) apps. It exists for two reasons: it is the reference implementation a module author can copy from, and it is the fixture the navigation performance benchmarks run against.

Unlike the placeholder `make new-module` scaffolds, this module exercises the realistic worst case — a foreign-key relation, an indexed text search, an enum status, audit and soft-delete mixins, and a composite index matching the default browse ordering.

## Install

```bash
pip install simple_module_catalog
```

Add `simple_module_catalog` to your host's dependencies and the entry point is discovered automatically.

## Usage

Two Inertia pages and a JSON API, both gated by the `catalog.view` permission:

| Route | Page | Purpose |
|---|---|---|
| `GET /catalog/` | `Catalog/Browse` | Paginated list with search, status filter and sort |
| `GET /catalog/{product_id}` | `Catalog/Detail` | Single product |
| `GET /api/catalog/products` | — | JSON list: `q`, `status`, `category_id`, `sort`, `page`, `page_size` |
| `GET /api/catalog/products/{id}` | — | Single product |
| `GET /api/catalog/categories` | — | All categories |

The view routes sanitize their query parameters rather than rejecting them — a bad `page` or `status` falls back to the default instead of returning 422, so a stale bookmark never shows a user an error page. The JSON API validates strictly, matching the convention in `audit_log`.

## What it demonstrates

- **Column-query listing.** `CatalogService.list_products` selects only the DTO's columns and counts the same conditions directly, rather than hydrating ORM objects per page.
- **Module-prefixed tables.** `catalog_product` / `catalog_category`, so they cannot collide in the host's single schema.
- **Migration branch label.** The first migration sets `branch_labels = ("catalog",)`, enabling `downgrade catalog@base`.
- **Constants over literals.** Permissions, page ids and route prefixes live in `constants.py`, as `scripts/check_hardcoded_strings.py` requires.
- **Indexes chosen for the actual queries.** The composite `(status, created_at)` matches the default browse ordering under a status filter.

## Seeding data

For benchmarking or local exploration, against a throwaway database:

```bash
SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest \
  uv run python tests/loadtest/seed_catalog.py 5000
```

The seed is idempotent — re-running it is a no-op unless you pass `--force`.

## Configuration

Settings use the `SM_CATALOG_*` prefix and are stored on `app.state.catalog`:

| Setting | Default | Purpose |
|---|---|---|
| `default_page_size` | `20` | Rows per page when the request omits `page_size` |
