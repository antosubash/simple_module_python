# simple-module-feature-flags

Feature flags for [simple_module](https://github.com/antosubash/simple_module_python) apps. Global flags with per-tenant overrides, a tiny consumer API, and no external service to run.

## Install

```bash
pip install simple-module-feature-flags
```

## What it provides

- `Flag` and `TenantFlagOverride` SQLModel tables.
- `is_enabled("flag.name", tenant_id=...)` consumer API.
- Admin UI at `/feature-flags/admin` — toggle flags, add tenant overrides.
- Cache layer so checking a flag on every request is cheap.

## Usage

Gate a route:

```python
from feature_flags import is_enabled   # type: ignore[import-not-found]
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/new-feature")
async def new_feature(tenant_id: int = Depends(current_tenant_id)):
    if not await is_enabled("orders.new_pricing_engine", tenant_id=tenant_id):
        raise HTTPException(404)
    return {"rolled_out": True}
```

Seed a flag in a migration or admin UI:

```python
# via migration
Flag(name="orders.new_pricing_engine", enabled=False)
```

Tenant override:

```python
TenantFlagOverride(tenant_id=7, flag_name="orders.new_pricing_engine", enabled=True)
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
