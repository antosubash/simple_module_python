# simple_module_feature_flags

Feature flags for [simple_module](https://github.com/antosubash/simple_module_python) apps. Global flags with per-tenant overrides, a tiny consumer API, and no external service to run.

## Install

```bash
pip install simple_module_feature_flags
```

## What it provides

- Flags are *declared* via the framework `register_feature_flags` hook (`FeatureFlagDefinition(name, default_enabled=...)`); the module persists only *overrides* in the `feature_flags_override` SQLModel table (scoped by `scope` / `scope_id`).
- `FeatureFlagRegistry.is_enabled("flag.name", tenant_id=...)` consumer API (resolution order: tenant override > system override > declared default).
- Admin UI at `/feature_flags` — toggle flags, add per-scope overrides.
- The registry is an in-memory cache hydrated from the DB so checking a flag on every request is cheap.

## Usage

Declare a flag in your module:

```python
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry


class OrdersModule(ModuleBase):
    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(FeatureFlagDefinition(name="orders.new_pricing_engine", default_enabled=False))
```

Gate a route using the registry dependency:

```python
from fastapi import APIRouter, HTTPException

from feature_flags.deps import FeatureFlagRegistryDep  # type: ignore[import-not-found]

router = APIRouter()


@router.get("/new-feature")
async def new_feature(flags: FeatureFlagRegistryDep):
    if not flags.is_enabled("orders.new_pricing_engine"):
        raise HTTPException(404)
    return {"rolled_out": True}
```

Overrides (system or per-tenant) are managed through the admin UI at `/feature_flags`.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
