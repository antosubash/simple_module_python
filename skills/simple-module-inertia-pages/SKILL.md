---
name: simple-module-inertia-pages
description: Use when adding or debugging an Inertia.js page in a simple_module_python module — TSX file naming, the inertia.render() namespace, shared props (auth, menus, i18n), or why a page renders blank or fires SM003/SM004. Triggers on "inertia.render", "page not found", "auth.user is null", "InertiaDep", or any edit involving pages/*.tsx in a module.
---

# simple_module_python: Inertia pages

## Render key → file mapping

`inertia.render("<Namespace>/<PageName>", props)` resolves to a single `.tsx` file. The mapping is exact and case-sensitive:

| Source | Render call | File location |
|---|---|---|
| Module page | `inertia.render("Orders/List", ...)` | `<module_pkg>/orders/pages/List.tsx` |
| Module page (snake-case dir) | `inertia.render("BlogPosts/Index", ...)` | `<module_pkg>/blog_posts/pages/Index.tsx` |
| Host page | `inertia.render("Landing", ...)` | `<host>/client_app/pages/Landing.tsx` |

The namespace is **`ModuleMeta.name`** — by default the PascalCase of the module's directory name (the scaffolder runs `to_pascal_case`), not the file system path. Directory `blog_posts` → `BlogPosts`. The manifest generator keys each module's glob by `meta.name` (`compute_module_pages` in `simple_module_hosting/manifest.py`), and `smpy host gen-pages` wires up Vite's `import.meta.glob` so the resolver (`host/client_app/pages.ts`) maps `"<meta.name>/<PageName>"` → the page module. A `.tsx` under a subdirectory of `pages/` is keyed by its relative path (`pages/admin/Edit.tsx` → `"<meta.name>/admin/Edit"`).

After adding or renaming a `.tsx`, regenerate the manifest:

```bash
smpy host gen-pages --host-dir=client_app
```

Boot regenerates it too; mid-session adds need the manual call before HMR sees them.

## Shared props (no setup needed)

`InertiaLayoutDataMiddleware` populates these on every Inertia response:

| Prop | Shape | Populated from |
|---|---|---|
| `auth.user` | object or `null` | A `principal_serializer` callable on `app.state` (registered by the `auth` module's `register_settings`) |
| `auth.isAuthenticated` | bool | `request.state.user` presence |
| `auth.permissions` | string[] | Roles → permissions expansion via the framework's permission registry |
| `menus` | `{ sidebar, adminSidebar, navbar, userDropdown }` | All modules' `register_menu_items()` output, auth/role-filtered |
| `i18n` | `{ locale, supportedLocales, messages }` | Active locale (`request.state.locale`) + flattened message bundle for that locale (`messages` is `null` on Inertia XHR partials when the locale is unchanged) |

**`auth.user` is `None` when no `principal_serializer` is registered**, even if the user is authenticated. The framework can't know the shape of your user object. The `auth` module registers the callable during `register_settings(app)` (`modules/auth/auth/module.py`):

```python
def _serialize_principal(user: UserContext) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "roles": user.roles}


class AuthModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.principal_serializer = _serialize_principal
```

## Endpoint pattern

Use `InertiaDep` from `simple_module_hosting.inertia_deps` — it injects an `Inertia` instance with shared props already attached:

```python
# orders/endpoints/views.py
from fastapi import APIRouter
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()


@router.get("/")
async def list_orders(inertia: InertiaDep, service: OrdersServiceDep):
    return await inertia.render("Orders/List", {"orders": await service.list()})
```

The `view_router` (mounted at `view_prefix`) is for HTML/Inertia. The `api_router` (mounted at `route_prefix`, e.g. `/api/orders`) is for JSON. Don't mix them.

## Inertia POST/PUT/DELETE → JSON `/api/*` is broken

Inertia's `router.post(...)` / `.patch(...)` / `.put(...)` / `.delete(...)` expects an Inertia response back, not JSON. If a page calls `router.post("/api/orders", ...)`, Inertia rejects the JSON response and the form silently fails.

Two fixes, in preference order:

1. **Stay Inertia-native** — point the call at a *view* endpoint (under `view_prefix`, e.g. `/orders/...`) that returns `RedirectResponse(..., status_code=303)`. Inertia follows the redirect and re-renders the page.
2. **Need the JSON payload back** — use plain `fetch()` against the `/api/*` endpoint instead of Inertia's `router`:

```tsx
await fetch("/api/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});
```

`SM018` warns when it spots Inertia `router.{post,patch,put,delete}()` targeting `/api/*` paths.

## Other gotchas

- **Translated strings in props built at module scope.** `const labels = { title: t("orders.title") }` freezes against the first render's locale — build per-request translations inside the handler or via shared props.
- **Imported a page TSX from another page.** Manifest-wired pages break if you import them directly; production builds drop the side-effect imports.
- **Pages exist but are unreachable in the UI (`SM019`).** A module with a non-empty `view_prefix` that overrides `register_routes` but neither `register_menu_items` nor `register_permissions` ships pages with no sidebar entry and no role-editor visibility. Add a menu item, register permissions, or clear `view_prefix` if it's API-only.

## Related skills

- **simple-module-creating** — where the PascalCase rule originates (matching `ModuleMeta.name`)
- **simple-module-doctor** — full reference for `SM003` / `SM004` / `SM018` / `SM019`
