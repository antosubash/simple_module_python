# simple_module_inertia

Inertia.js **v3** server adapter for FastAPI. This is the protocol half of a
simple_module app's React frontend: it turns `inertia.render("Users/Index", props)`
into either the JSON page object an Inertia visit expects or the HTML document a
full page load expects, and implements every v3 prop type (`optional`, `always`,
`defer`, `merge`, `prepend`, `deep_merge`, `once`, `scroll`).

Forked from [fastapi-inertia](https://github.com/hxjo/fastapi-inertia) (MIT) —
see `NOTICE`. Precognition and SSR are not implemented.

## Protocol coverage

The compatibility target is **Inertia v3**, with `@inertiajs/core` **3.x** on
the client. Coverage below describes this adapter's server behavior; client
features still require the corresponding Inertia client API.

| Feature | Status | Coverage |
|---|---|---|
| Page object | Implemented | `component`, `props` (including an always-present `errors` object), root-relative `url`, and `version`, in both HTML and JSON responses. |
| Partial reloads | Implemented | Matching `X-Inertia-Partial-Component` with `X-Inertia-Partial-Data` and/or `X-Inertia-Partial-Except`; dotted dictionary paths and filtering before loaders run. |
| Prop types | Implemented | Composable `optional`, `always`, `defer` (groups and `rescue=True`), `merge`, `prepend`, `deep_merge`, `once`, and `scroll`; merge factories accept `match_on`. |
| Prop metadata | Implemented | Conditional `deferredProps`, `rescuedProps`, `mergeProps`, `prependProps`, `deepMergeProps`, `matchPropsOn`, `onceProps`, `scrollProps`, and `sharedProps`. `X-Inertia-Except-Once-Props` skips resolving cached once props, and `X-Inertia-Infinite-Scroll-Merge-Intent` picks append or prepend for scroll props. |
| Reset | Implemented | `X-Inertia-Reset` suppresses merge metadata for named prop paths and sets the corresponding scroll reset flag. |
| Asset versioning | Implemented | Inertia GETs with a missing or stale `X-Inertia-Version` receive 409 with `X-Inertia-Location` and the server's `X-Inertia-Version`. |
| Redirects and middleware | Implemented | `inertia.redirect()` (and `back()`) answer 303 for non-GET requests and 307 for GET; middleware also converts 302/307 after PUT/PATCH/DELETE/QUERY. Redirects whose target has a `#fragment` become an empty 409 with `X-Inertia-Redirect` (`inertia.redirect_with_fragment()` emits it directly; the automatic conversion skips prefetch). Explicitly empty 200 responses redirect back with 303; HTML and Inertia responses include `Vary: X-Inertia`. |
| External navigation | Implemented | `inertia.location(url)` returns 409 with `X-Inertia-Location` for a client-side full-page navigation. |
| History and fragments | Implemented | `inertia.encrypt_history()`, `inertia.clear_history()`, and `inertia.preserve_fragment()` emit `encryptHistory`, `clearHistory`, and `preserveFragment`; the client performs encryption and history updates. |
| Validation | Implemented | Validation conversion keeps the first message per top-level field; `X-Inertia-Error-Bag` scopes session errors, which render only with `use_flash_errors` (hosting enables it). The standalone validation handler redirects back; hosting's form helper does likewise, while hosting's request-validation handler renders an error page. |
| Hosting error pages | Implemented | `simple_module_hosting` renders the `Error` component for supported browser/Inertia errors, preserving the HTTP status and exception headers; API requests retain JSON errors. |
| Test helper | Implemented | `simple_module_test.InertiaPage.from_response(response)` (or `inertia_page(response)`) parses HTML/JSON pages, offers fluent page/prop assertions, and follows partial reloads and deferred groups with `reload_only`, `reload_except`, and `load_deferred`. |
| SSR | Not implemented | No SSR client: `ssr_url` and the template's SSR branches are unused, and `ssr_enabled` only makes asset resolution read the Vite manifest. Tracked in [#580](https://github.com/antosubash/simple_module_python/issues/580). |
| Live props | Not implemented | No live prop protocol support. |
| Precognition | Not implemented | No predictive validation integration. |
| DevTools | Not implemented | No DevTools integration. |
| `preserveBigIntegers` | Not implemented | No big-integer marker protocol. |
| Page `flash` / `inertia:flash` | Not implemented | The protocol `flash` page field is never emitted. `inertia.flash()` writes a session-backed `messages` prop (`flash_message_key`) only when `use_flash_messages` is set; hosting leaves it off, so there `flash()` raises `NotImplementedError`. |

## Install

`simple_module_hosting` depends on this package, so any app scaffolded with
`smpy new` already has it. To use the adapter on its own:

```bash
uv add simple_module_inertia
```

## Usage

Inside a simple_module app, reach the per-request `Inertia` instance through
`InertiaDep` and import the response type and prop factories from here:

```python
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia import InertiaResponse, defer, merge, optional


async def index(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(
        "Feed/Index",
        {
            "posts": merge(load_posts, match_on="id"),  # append on navigation
            "analytics": defer(load_analytics),  # loaded after first paint
            "stats": optional(load_stats),  # only on partial reloads that ask
        },
    )
```

Standalone, configure it once, install the middleware and register the version-conflict handler:

```python
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from simple_module_inertia import (
    Inertia,
    InertiaConfig,
    InertiaMiddleware,
    InertiaVersionConflictException,
    inertia_dependency_factory,
    inertia_version_conflict_exception_handler,
)

config = InertiaConfig(
    templates=Jinja2Templates(directory="templates"),
    entrypoint_filename="main.tsx",
    root_directory=".",
    dev_url="http://localhost:5173",
)
inertia_dep = inertia_dependency_factory(config)

app = FastAPI()
app.add_middleware(InertiaMiddleware)
app.add_exception_handler(
    InertiaVersionConflictException, inertia_version_conflict_exception_handler
)


@app.get("/")
async def home(inertia: Inertia = Depends(inertia_dep)):
    return await inertia.render("Home", {"greeting": "hello"})
```

The root template needs `{% inertia_head %}` in `<head>` and `{% inertia_body %}`
in `<body>`; the page object lands once in
`<script data-page="app" type="application/json">…</script>`, followed by
`<div id="app"></div>`.

The middleware normalizes mutation redirects (302/307 to 303), fragment redirects
(409 with `X-Inertia-Redirect`, except prefetch), and empty 200 responses (303 back
to a safe same-site Referer). It adds `Vary: X-Inertia` to Inertia and HTML
responses without buffering streams. Inertia GETs that inject the dependency
must send the current `X-Inertia-Version`; a missing or stale version receives
409 with `X-Inertia-Location` and the server's `X-Inertia-Version`.
Hosting installs this middleware and exception handler automatically.

## Prop resolution

Partial reloads accept dotted paths in `X-Inertia-Partial-Data` and
`X-Inertia-Partial-Except`, such as `auth.user`. Filtering traverses plain
Python dictionaries before running loaders. A callable, awaitable or `Prop`
resolves its children in full; `always()` also bypasses partial filters.
Merge and once metadata on partial reloads follows the selected paths.

`once(value, key=None, expires_at=None)` announces its cache key even when a
full Inertia visit omits its cached value. Partial reloads ignore
`X-Inertia-Except-Once-Props` and refresh requested once props.

`scroll(value, ..., reset=False, wrapper="data")` labels `<prop>.data` for
merging by default. A value that resolves to a bare list merges at the prop
root automatically. Set `wrapper` to another dictionary path, or `None` to
merge a dictionary value at the prop root. The infinite-scroll merge-intent header
chooses append or prepend. The explicit `reset=True` argument or a prop path
in `X-Inertia-Reset` sets `scrollProps[path].reset` and suppresses merge labels.

`defer(value, group="default", rescue=False)` supports `rescue=True` for
loaders that may fail. A failed rescued loader logs its exception, leaves the
prop out of the response, and adds its path to `rescuedProps` so the client's
`<Deferred>` rescue slot can render. Other props still resolve; without
`rescue=True` the exception propagates. Deferred props are announced without
running their loaders on full visits. All wrappers compose through `Prop`,
for example `once(merge(defer(load_analytics, rescue=True)))`.
