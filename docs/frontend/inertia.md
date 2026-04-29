# Inertia basics

Inertia.js turns classic server-side routing into a single-page app without a separate API. The server returns a JSON payload describing which React page to render and what props to pass; the client's Inertia runtime swaps in the page component with a `fetch`-level round-trip. No bespoke API, no client-side router, no state-sync code.

## What's on the server

Two moving parts:

1. **`fastapi-inertia`** — renders templates and serializes responses in Inertia's expected shape.
2. **`InertiaLayoutDataMiddleware`** (framework) — attaches shared props (`auth`, `menus`, `i18n`) to every response.

## Rendering a page

```python
# modules/orders/orders/endpoints/views.py
from fastapi import APIRouter
from simple_module_hosting.inertia_deps import InertiaDep

from orders.contracts.schemas import OrderOut
from orders.deps import OrderServiceDep

router = APIRouter()

@router.get("")
async def browse(inertia: InertiaDep, service: OrderServiceDep):
    orders: list[OrderOut] = await service.list()
    return await inertia.render(
        "Orders/Browse",
        props={"orders": [o.model_dump(mode="json") for o in orders]},
    )
```

Breakdown:

- `InertiaDep` is a request-scoped dependency provided by fastapi-inertia. It's attached to `app.state.inertia_dependency` at boot.
- The first argument to `render` is the **page key** — `"Orders/Browse"` maps to `modules/orders/orders/pages/Browse.tsx`. See [Pages & discovery](/frontend/pages).
- `props` is a plain dict serialized to JSON. Use `model_dump(mode="json")` on SQLModel DTOs to get JSON-safe types (`Decimal → str`, `datetime → iso string`).

## Responding with JSON vs. Inertia

- **`endpoints/api.py`** — returns JSON. Called by background/non-Inertia code, or by Inertia's `router.get/post` on the client (which sends `X-Inertia: true` and receives a full Inertia response, **not** raw JSON).
- **`endpoints/views.py`** — returns Inertia pages. Routed at `view_prefix`, rendered as full HTML on the first request and as JSON page updates on client-side navigation.

The split is convention: keep GET-for-page-data calls in `views.py`, keep POST/PATCH/DELETE data mutations in `api.py` even if triggered from Inertia forms. This way JSON APIs are usable from scripts and Inertia pages route cleanly.

## Inertia form submission

From a page, use Inertia's `router.post`:

```tsx
import { router } from "@inertiajs/react";

function CreateOrder() {
  const [data, setData] = useState({ customer_email: "", total: "" });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        router.post("/api/orders", data);
      }}
    >
      ...
    </form>
  );
}
```

Inertia sends the request with the `X-Inertia` header and expects an Inertia response back (a redirect or a page render). **Do not** point Inertia's `router.post` at a JSON endpoint — fastapi-inertia sees a non-Inertia response and throws.

This is exactly what diagnostic `SM018` warns about: an `api.py` route that returns JSON, called from a page via `router.post/patch/put/delete`. Either:

- Change the endpoint to live in `views.py` and return `inertia.render(...)` or a redirect.
- Or change the page code to use `fetch(...)` for a true JSON call.

## Redirect-after-post

Inertia expects a redirect response (302/303) after a successful mutation:

```python
# modules/orders/orders/endpoints/views.py
from fastapi.responses import RedirectResponse

@router.post("")
async def create(
    data: OrderCreate, inertia: InertiaDep, service: OrderServiceDep
):
    order = await service.create(data)
    return RedirectResponse(f"/orders/{order.id}", status_code=303)
```

Inertia's client follows the redirect and renders the new page.

## Flash messages

For "created successfully" toasts, use Starlette's session to flash a message:

```python
request.session["flash"] = {"type": "success", "message": "Order created"}
return RedirectResponse("/orders", status_code=303)
```

Then expose it in the shared props — `InertiaLayoutDataMiddleware` already reads `request.session.pop("flash", None)` and attaches it to `request.state.inertia_shared["flash"]`.

## What the shared props look like

Every Inertia response includes:

```ts
{
  auth: {
    user: { id, email, full_name, ... } | null,
    isAuthenticated: boolean,
    permissions: string[],
  },
  menus: {
    sidebar: MenuItem[],
    adminSidebar: MenuItem[],
    navbar: MenuItem[],
    userDropdown: MenuItem[],
  },
  i18n: {
    locale: string,
    bundle: Record<string, string>,   // flat key → value
  },
  flash: { type: string, message: string } | null,
}
```

Accessed from any page via `usePage().props.auth` etc., or via typed helpers from `@simple-module-py/ui` (`useAuth`, `useMenus`, `useT`).

## Frontend runtime setup

`host/client_app/src/main.tsx` bootstraps Inertia:

```tsx
import { createInertiaApp } from "@inertiajs/react";
import { resolvePage } from "./modules.generated";

createInertiaApp({
  resolve: resolvePage,
  setup: ({ el, App, props }) => {
    createRoot(el).render(<App {...props} />);
  },
});
```

`resolvePage` is generated by `make gen-pages` from the module manifest. It maps a page key (e.g. `"Orders/Browse"`) to a dynamic import of the matching `.tsx` file.

## CSRF

There is no explicit CSRF token middleware. Protection comes from `SameSite=Lax` on the session cookie:

- Browsers don't attach the session cookie to **cross-site** POST/PUT/DELETE.
- A forged form-submit from another origin arrives without authentication, so it's 401/403.
- Same-site form submissions work normally.

This is sufficient because Inertia mutations go through `fetch`, which honors `SameSite`. Raw `fetch()` calls in page code don't need a CSRF header.
