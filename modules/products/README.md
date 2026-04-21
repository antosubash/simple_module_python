# simple_module_products

Example CRUD module for [simple_module](https://github.com/antosubash/simple_module_python). **This is a reference / demo**, not a production-ready commerce module — it exists to show what a fully-featured `simple_module` module looks like end-to-end: `ModuleBase`, SQLModel table with `AuditMixin`, contracts, service, REST + Inertia endpoints, Browse/Create/Edit pages, tests.

Fresh `simple-module new` scaffolds *don't* include this by default — it's here as a readable example.

## Install

```bash
pip install simple_module_products
```

## What it provides

- `Product` SQLModel table with `name`, `sku`, `price_cents`, `AuditMixin`.
- Contracts (`ProductCreate`, `ProductUpdate`, `ProductRead`) under `products.contracts`.
- Service layer (`ProductsService`) encapsulating the (tiny) business logic.
- REST endpoints at `/api/products` + Inertia view endpoints at `/products`.
- Inertia pages `Products/Browse`, `Products/Create`, `Products/Edit`.
- Unit tests covering the service + integration tests hitting the full endpoint stack.

## Usage

It's a reference, so the most useful "usage" is reading the source:

- `modules/products/products/module.py` — the `ModuleBase` subclass.
- `modules/products/products/service.py` — business logic.
- `modules/products/products/pages/` — Inertia React pages.
- `modules/products/tests/` — the test patterns to copy into new modules.

If you do want a working `/products` in your own app:

```bash
uv add simple_module_products
# Alembic will now see the products schema at the next `alembic revision --autogenerate`.
```

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
