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

- `InertiaDep` (from `simple_module_hosting.inertia_deps`) is a request-scoped dependency that resolves the `Inertia` instance from `app.state.inertia_dependency` (configured at boot) and shares in `request.state.inertia_shared`.
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
async def create(data: OrderCreate, inertia: InertiaDep, service: OrderServiceDep):
    order = await service.create(data)
    return RedirectResponse(f"/orders/{order.id}", status_code=303)
```

Inertia's client follows the redirect and renders the new page.

## Toasts

There is no `flash` shared prop. For "created successfully" toasts, fire `sonner`'s `toast` directly from the page's request callback:

```tsx
import { toast } from "sonner";

router.post("/api/orders", data, {
  onSuccess: () => toast.success("Order created"),
});
```

Server-side validation errors arrive on the page's `errors` prop (fastapi-inertia's `use_flash_errors`, enabled in the Inertia config).

## What the shared props look like

Every Inertia response includes:

```ts
{
  auth: {
    user: { id, name, email, roles } | null,
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
    supportedLocales: string[],
    messages: Record<string, string> | null,   // flat key → value; null on unchanged-locale XHR partials
  },
}
```

Accessed from any page via `usePage().props.auth` etc. (the exported `SharedProps` type from `@simple-module-py/ui` covers `auth` + `menus`); translations come from `useT()` in `@simple-module-py/i18n`. See [Shared props & layout](/frontend/shared-props).

## Frontend runtime setup

`host/client_app/main.tsx` imports `./styles.css` and `./app`; `app.tsx` bootstraps Inertia:

```tsx
import { createInertiaApp } from "@inertiajs/react";
import { resolvePage } from "./pages";

createInertiaApp({
  resolve: (name) => resolvePage(name),
  setup({ el, App, props }) {
    createRoot(el).render(<App {...props} />);
  },
});
```

`resolvePage` lives in `host/client_app/pages.ts` (hand-written). It builds a page-key → loader map from `moduleGlobs` (the `import.meta.glob` calls in the generated `modules.generated.ts`) plus the host's own `./pages/**/*.tsx` glob, mapping a page key (e.g. `"Orders/Browse"`) to a dynamic import of the matching `.tsx` file.


## Link navigation

The app is client-rendered: the root template ships `<div id="app"></div>` empty
and `app.tsx` fills it. So a navigation that creates a **new document** shows a
blank white page until the bundle has booted — which is what a plain
`<a href="/somewhere">` does.

Admin screens use Inertia's `<Link>` and are fine. The problem is authored
content: pagebuilder widgets, and the markdown and rich-text fields inside them,
turn author-entered URLs into plain anchors. An anchor that comes out of a
markdown parser has no component to swap for a `<Link>`.

`app.tsx` therefore calls `startSpaLinkInterception()` once, before the first
render:

```tsx
import { startSpaLinkInterception } from "@simple-module-py/ui/lib/spa-links";

setup({ el, App, props }) {
  startSpaLinkInterception();
  createRoot(el).render(<App {...props} />);
}
```

It delegates one `click` listener on the document and routes same-origin page
links through `router.visit()`, whatever produced the anchor. It runs in the
bubble phase, so a `<Link>` — which cancels the event itself — is already
`defaultPrevented` and is left alone rather than visited twice.

The bias is towards **not** interfering. These keep the browser's own behaviour:

| Left alone | Why |
| --- | --- |
| Another origin, or a non-http scheme (`mailto:`, `tel:`) | Not ours to route |
| A path whose last segment looks like a file (`/media/report.pdf`) | Inertia would request it expecting a page and raise its error modal over the download |
| `#`, `#section`, or a link to the current path | The browser scrolls correctly; `href="#"` is also what an unfilled pagebuilder nav row holds |
| `download`, `target` other than `_self`, `rel="external"` | The author asked for it |
| `data-native-link` | Explicit opt-out for anything the rules miss |
| Anything inside `[data-puck-preview]` / `[data-puck-component]` | A Puck editor rendering without an iframe puts the edited page's real anchors in the admin document |
| Modified clicks (⌘/ctrl/shift/alt) and non-left buttons | Open-in-new-tab must keep working |

As a backstop, a visit that comes back **without** an `x-inertia` header is
handed to the browser as a hard navigation, so a URL that turns out not to be a
page still resolves instead of raising the error modal.

`smpy new` wires this into the app template. An app scaffolded before this
landed owns its own `app.tsx` and must add the call itself.

## CSRF

There is no explicit CSRF token middleware. Protection comes from `SameSite=Lax` on the session cookie:

- Browsers don't attach the session cookie to **cross-site** POST/PUT/DELETE.
- A forged form-submit from another origin arrives without authentication, so it's 401/403.
- Same-site form submissions work normally.

This is sufficient because Inertia mutations go through `fetch`, which honors `SameSite`. Raw `fetch()` calls in page code don't need a CSRF header.
