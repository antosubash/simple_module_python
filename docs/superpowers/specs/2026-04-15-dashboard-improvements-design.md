# Dashboard Improvements: Real Stats + System Info

**Date:** 2026-04-15
**Status:** Draft
**Module:** `modules/dashboard`

## Goal

Replace the current placeholder dashboard with a data-rich overview showing real user/product counts and system information. Activity logging and audit trails are out of scope — a separate audit log module will handle that.

## Current State

The dashboard (`modules/dashboard/dashboard/pages/Home.tsx`) renders:

- 3 stat cards with hardcoded/placeholder values (Products: "-", Users: "-", Modules: "3")
- A static welcome card
- In-memory product event counters (not persisted, lost on restart)

The backend view endpoint passes only a `welcome` string to the frontend via Inertia.

## Design

### Section 1: Stat Cards (replace placeholders with real data)

Four stat cards in a responsive grid:

| Card | Source | Query |
|------|--------|-------|
| **Total Users** | `users_user` table | `SELECT COUNT(*) FROM users_user` |
| **Active Users** (7d) | `users_user.last_login_at` | `WHERE last_login_at >= NOW() - INTERVAL '7 days'` |
| **Products** | `products_product` table | `SELECT COUNT(*) FROM products_product` |
| **Modules** | `discover_modules()` | `len(discover_modules())` |

The stat card grid changes from 3 to 4 columns: `grid-cols-1 sm:grid-cols-2 md:grid-cols-4`.

Active Users gets a new accent color (amber) to differentiate from Total Users (emerald stays for total).

### Section 2: System Info Panel

A card displayed below the stat cards showing:

- **Loaded modules** — name and status badge (green dot) for each discovered module
- **Python version** — from `sys.version`
- **Health checks** — results from `app.state.health_registry` with green/yellow/red status indicators

### Section 3: Dashboard Stats API (updated)

Expand `GET /api/dashboard/stats` to return all data the frontend needs:

```python
@router.get("/stats")
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "total_users": <count from users_user>,
        "active_users_7d": <count where last_login_at >= 7 days ago>,
        "total_products": <count from products_product>,
        "module_count": <len(discover_modules())>,
        "system_info": {
            "modules": [
                {"name": "Auth", "status": "loaded"},
                {"name": "Users", "status": "loaded"},
                {"name": "Products", "status": "loaded"},
                {"name": "Dashboard", "status": "loaded"},
            ],
            "python_version": "3.12.x",
            "health_checks": [
                {"name": "database", "status": "healthy"},
            ],
        },
    }
```

Cross-module DB queries: The stats endpoint queries `users_user` and `products_product` tables directly (same database). This is a read-only cross-module query, acceptable for an aggregation endpoint.

### Section 4: Dashboard View Endpoint (updated)

The Inertia view endpoint (`GET /dashboard`) passes all stats as page props:

```python
@router.get("/")
async def dashboard(inertia: InertiaDep, t: TranslatorDep, db: ...) -> InertiaResponse:
    stats = await fetch_dashboard_stats(db, request)
    return await inertia.render("Dashboard/Home", {
        "welcome": t.t("dashboard.home.welcome_message"),
        **stats,
    })
```

### Section 5: Frontend — Home.tsx (rewritten)

The page receives all stats as Inertia page props and renders:

1. **Stat Cards Row** — 4-column responsive grid with real values
2. **System Info Panel** — card listing modules, Python version, health checks

**System Info Panel:**
- Card listing loaded modules with status badges (green dot for loaded)
- Python version display
- Health check results with status indicator (green/yellow/red dot)
- Wrapped in a `Card` with title "System"

### Section 6: i18n Updates

Add new translation keys to `modules/dashboard/dashboard/locales/en.json` (and `es.json`):

- `stats.active_users`: "Active Users (7d)"
- `system_info_title`: "System"
- `system_info.modules`: "Modules"
- `system_info.python_version`: "Python Version"
- `system_info.health_checks`: "Health Checks"

### Section 7: Cleanup

Remove the in-memory product event counters from `handlers.py` since they serve no purpose without the activity log. The dashboard module still depends on Products (for the product count query) but no longer subscribes to product events.

## Files to Modify

| File | Changes |
|------|---------|
| `modules/dashboard/dashboard/handlers.py` | Remove in-memory counters (file may become empty/deleted) |
| `modules/dashboard/dashboard/module.py` | Remove event handler subscriptions, add `depends_on=["Users"]` |
| `modules/dashboard/dashboard/endpoints/api.py` | Expand `/stats` with real counts + system info |
| `modules/dashboard/dashboard/endpoints/views.py` | Pass full stats as Inertia props |
| `modules/dashboard/dashboard/pages/Home.tsx` | Rewrite with real stat cards + system info panel |
| `modules/dashboard/dashboard/locales/en.json` | Add new translation keys |
| `modules/dashboard/dashboard/locales/es.json` | Add new translation keys |
| `modules/dashboard/pyproject.toml` | Add dependency on `users` |
| `modules/dashboard/tests/test_dashboard.py` | Rewrite tests for new stats endpoint |

## Out of Scope

- Activity/audit logging (separate module)
- Event handler persistence
- Recent activity feed
- Activity charts
- Real-time updates
- Dashboard customization
