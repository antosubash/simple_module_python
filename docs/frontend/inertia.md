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

- **`endpoints/api.py`** returns JSON. Use the typed `createApi` client wrapped in
  `apiResult` for JSON actions, and toast failed results (including network failures).
- **`endpoints/views.py`** returns Inertia pages or redirects. View-route forms use
  Inertia `useForm` for data, validation errors and processing state. Small actions
  without form fields may use `router.post/delete` with an `onError` toast.
  Handle `onHttpException` and `onNetworkError` too when an action should toast
  HTTP or connection failures; returning `false` suppresses Inertia's default handler.

## Inertia form submission

Submit to the module's view route:

```tsx
import { useForm } from "@inertiajs/react";

function CreateOrder() {
  const form = useForm({ customer_email: "", total: "" });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        form.post("/orders", {
          onError: () => toast.error(t(keys.orders.create.failed)),
        });
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
- Or change the page code to call the endpoint through the module's typed API client (see [JSON calls from pages](#json-calls-from-pages)).

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

router.post("/orders", data, {
  onSuccess: () => toast.success(t(keys.orders.create.saved)),
  onError: () => toast.error(t(keys.orders.create.failed)),
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

Accessed from any page via `usePage().props.auth` etc. (typed globally from `SharedProps` in `@simple-module-py/ui`, which covers `auth`, `menus` and `i18n`); translations come from `useT()` in `@simple-module-py/i18n`. See [Shared props & layout](/frontend/shared-props).

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


## SEO head

Crawlers and link unfurlers (Slack, LinkedIn) do not run JS, so a React `<Head>` is invisible to
them. Pass a `Head` to `inertia.render` and the first (document) response carries the tags:

```python
from simple_module_inertia import Head

return await inertia.render(
    PAGE_PUBLIC,
    {"page": page},
    head=Head(
        title=page.title,
        description=page.summary,
        canonical=f"/p/{page.slug}",
        og={"image": page.cover_url, "type": "article"},
        twitter={"card": "summary_large_image"},
        json_ld=[{"@context": "https://schema.org", "@type": "Article", "name": page.title}],
    ),
)
```

- `title` gets the app-name suffix, as `<Head title>` does. `og:title`, `og:description` and
  `og:url` default from `title`, `description` and `canonical`; set them in `og` to override.
- URL fields (`canonical`, and `og`/`twitter` keys `url`, `image`, `image:url`, `video`, `audio`)
  must be `http(s)` or a site-relative path; anything else (`javascript:`, `data:`, `//host`) raises
  a validation error when the `Head` is built. Text is HTML-escaped; JSON-LD is serialised so
  `</script>` and `<!--` inside a value cannot end the element.
- Relative URLs are joined onto the **`public_base_url`** host setting (Settings, read on every
  request, no restart). The request `Host` is never used, because it is client-controlled. While
  it is unset, relative canonical / image URLs are omitted rather than guessed, so set it on any
  install that serves public pages.
- Every tag carries a `data-inertia` key, which is how Inertia's client head manager replaces an
  element instead of appending a duplicate. The same tags are sent as the `_head` prop and
  `app.tsx` passes `serverHead: resolveServerHead` (`@simple-module-py/ui/lib/server-head`), so
  client-side visits keep the head in step with no per-page code. A page that passes no `head` falls
  back to the branded default title.
- A custom root template needs `{% inertia_head %}` plus
  `{% if not (inertia and inertia.has_head_title) %}<title ...>{% endif %}` around its static
  title (the shipped `host/templates/index.html` does this).

This is server-rendered **head** only; body SSR (a Node sidecar) is a separate step in #535.

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

The baseline is `SameSite=Lax` on the session cookie:

- Browsers don't attach the session cookie to **cross-site** POST/PUT/DELETE.
- A forged form-submit from another origin arrives without authentication, so it's 401/403.
- Same-site form submissions work normally.

Inertia forms need nothing more. A module that wants defence in depth puts
`RequiresCsrf` from `simple_module_hosting.csrf` on its API router; the check
then wants the session's token in an `X-CSRF-Token` header on
POST/PUT/PATCH/DELETE (safe methods are never checked).

Every **signed-in** page carries that token as the `csrfToken` shared prop.
Anonymous pages never do (nothing is minted into their session, so a public
page stays cacheable and never hands one visitor's token to the next), and an
API-token principal renders as anonymous. The typed API client below reads the
prop and sends the header itself, only to the page's own origin, so page code
never handles the token. A page may still receive its own token prop (the
api_tokens pages do) and pin it per call with `headers`.

## JSON calls from pages

Each module calls its `/api/*` routes through a typed client (#504):

```ts
// <pkg>/pages/api.ts
import { createApi } from '@simple-module-py/ui/lib/api';
import type { paths } from './api.generated';

export const api = createApi<paths>();
```

```tsx
import { apiResult } from '@simple-module-py/ui/lib/api';
import { api } from './api';

const result = await apiResult(
  api.POST('/api/tenants/{tenant_id}/switch', { params: { path: { tenant_id: id } } }),
);
if (!result.ok) toast.error(result.detail ?? t(keys.tenants.errors.generic));
```

- `createApi<paths>()` is an [`openapi-fetch`](https://openapi-ts.dev/openapi-fetch/)
  client: paths, parameters, bodies and responses are checked against the
  module's routes. It sends `credentials: 'same-origin'`, `Accept:
  application/json` and the `csrfToken` prop.
- `apiResult(call)` normalises any call to `{ ok, status, data, detail,
  fieldErrors, error }`. `detail` is the server's string `detail` (a message or
  a stable error code), `fieldErrors` maps each 422 error's last `loc` element
  to its `msg`, `error` is the raw error body (for codes that carry more, like
  a limit), and a request that never reached the server is `status: 0` instead
  of a thrown exception. The wrapper holds no English text.
- `useApiErrorToast(fallbackKey)` (`@simple-module-py/ui/hooks/use-api-error-toast`)
  returns a function that toasts `detail ?? t(fallbackKey)` for a failed result.
- `apiFetch<T>(url, { method, json })` is the untyped twin with the same
  conventions and result shape, for routes outside the module's schema (another
  module's route, a server-supplied URL, `/setup/*`) and multipart uploads.

`pages/api.generated.ts` is generated, committed and never edited: run
`smpy openapi gen-types --module <pkg>` (in the framework repo `make
gen-api-types`, which regenerates every module that has the file) after
changing a route or DTO. It needs Node: a local `openapi-typescript` is used
when installed, otherwise `npx` fetches the pinned version. A route without
`response_model` or a return annotation generates an `unknown` body, and the
command lists it. CI fails when a committed file is stale
(`make ci-api-types-fresh`). New modules from `smpy create-module` /
`make new-module` ship the client, the generated file and a Browse page that
deletes through it.
