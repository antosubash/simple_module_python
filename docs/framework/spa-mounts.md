# Legacy SPA mounts

Porting a large app step by step means running its existing client-routed SPA
next to new Inertia pages for a while. A module serves the SPA's build output
under a prefix by overriding `ModuleBase.spa_mounts()`:

```python
from pathlib import Path

from simple_module_core import ModuleBase, SpaMount


class LegacyModule(ModuleBase):
    def spa_mounts(self) -> list[SpaMount]:
        return [SpaMount("/legacy", Path(__file__).parent / "dist", auth="required")]
```

`SpaMount(prefix, dist_dir, index="index.html", auth="required" | "public")`.
A mount whose `dist_dir/index` does not exist (the SPA was not built) is skipped
with a warning.

## What is served

- `GET`/`HEAD` only; other methods are refused.
- A file that exists is served as is. Content-hashed files (`index-3f9a8c21.js`)
  get `Cache-Control: public, max-age=31536000, immutable`.
- A missing path **without an extension** whose request accepts `text/html`
  (`/legacy/datasets/123`) is answered with `index.html`, `Cache-Control: no-cache`,
  so the SPA's router takes over.
- A missing asset (`/legacy/missing.js`) or a missing path that does not accept
  HTML is a plain 404, never HTML.
- No filesystem path is built from the request: lookups go through `StaticFiles`,
  paths containing `..` are refused, and the fallback only ever serves the
  configured index file.

## Authentication

`auth="required"` (the default) leaves the mount behind `AuthMiddleware`:
an anonymous visitor is redirected to login. `auth="public"` registers the prefix
in the [public route registry](/framework/public-routes) for `GET`/`HEAD` only.
CSP applies as for any response; whitelist external origins the SPA needs with
`register_csp_sources`.

## Boot check

A prefix that overlaps a module's route/view prefix, a `static_mounts()` prefix,
a framework path or another SPA mount fails boot with
[`SM032`](/reference/diagnostic-codes), in every environment.

## Inertia link interception

The Inertia client turns same-origin link clicks into Inertia visits
(`startSpaLinkInterception`). Links into a legacy SPA must stay full navigations,
so the server publishes a shared prop `nativePrefixes`: the mounted SPA prefixes
(with a trailing slash) plus the DB-backed host setting `native_link_prefixes`
(a list such as `["/docs/"]`, editable under Settings, read per request).
`host/client_app/app.tsx` passes them to the interceptor:

```ts
startSpaLinkInterception({ exclude: (url) => isExcluded(url, nativePrefixes) });
```

`exclude` also accepts a prefix string or a list of prefixes. An Inertia
`<Link>` or `router.visit()` pointing into a mount is not covered; use a plain
`<a href>` there. Links inside the SPA are never touched, because the SPA is its
own document without the Inertia client.
