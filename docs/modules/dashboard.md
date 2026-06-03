# dashboard

The authenticated landing page. Renders a small system overview: total users, active users in the last 7 days, installed module list, Python version, and health-check results.

It's intentionally simple — a place for new installs to land that proves the pipeline is wired up. Replace it (or set `SM_MODULES_ENABLED` without `dashboard`) once you have your own home page.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Dashboard` |
| `route_prefix` | `/api/dashboard` |
| `view_prefix` | `/dashboard` |
| `depends_on` | `["Users"]` |

## Routes

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /dashboard/` | `Dashboard/Home` | authenticated user (any role) |

### API

| Method + path | Returns | Permission |
|---|---|---|
| `GET /api/dashboard/stats` | `dict` (see below) | authenticated user (any role) |

`/api/dashboard/stats` is what the page itself calls; you can hit it from your own UI or scripts. Response shape:

```json
{
  "total_users": 12,
  "active_users_7d": 3,
  "module_count": 8,
  "system_info": {
    "python_version": "3.12.4",
    "modules": ["Auth", "Users", ...],
    "health_checks": {"database": "ok", "redis": "ok"}
  }
}
```

The result is cached process-wide for 30 seconds. If you mutate something that should change the numbers (e.g. seed users from a script), call `dashboard.stats.invalidate_stats_cache()` to clear it on the next call.

## Menu

| Label | URL | Icon | Section | Order |
|---|---|---|---|---|
| `Dashboard` | `/dashboard/` | `home` | `SIDEBAR` | `10` |

## Permissions

_(none registered)_ — the page is gated by authentication only, via the `users` module's `AuthMiddleware`.

## Inertia pages

- `Dashboard/Home.tsx` — single page rendering the stats card, system info card, and welcome card. Kept simple on purpose so it's a useful starting template for a custom landing page.

## Locales

Top-level keys in `dashboard/locales/en.json`:

- `home.title`, `home.welcome_message`, `home.description`
- `home.stats.total_users`, `home.stats.active_users`, `home.stats.modules`
- `home.system_info_title`, `home.system_info.python_version`, `home.system_info.health_checks`, `home.system_info.modules`
- `home.welcome_card_title`, `home.description_body`

## Replacing it

If you want a different post-login landing page, set `users.login_redirect_url` in the [admin settings UI](/modules/settings) (or via `smpy settings import-from-env` from `SM_USERS_LOGIN_REDIRECT_URL`) to your route. You can keep the dashboard module installed for the menu entry, or set `SM_MODULES_ENABLED` without `dashboard` to drop it entirely. The `users` module auto-detects whether `dashboard` is installed; if not, it redirects to the first other module that exposes view routes (e.g. the GIS module on apps like smpy_gis), falling back to `/` only as a last resort.
