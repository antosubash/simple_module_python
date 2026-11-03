# simple_module_inertia

Inertia.js **v3** server adapter for FastAPI. This is the protocol half of a
simple_module app's React frontend: it turns `inertia.render("Users/Index", props)`
into either the JSON page object an Inertia visit expects or the HTML document a
full page load expects, and implements every v3 prop type (`optional`, `always`,
`defer`, `merge`, `prepend`, `deep_merge`, `once`, `scroll`).

Forked from [fastapi-inertia](https://github.com/hxjo/fastapi-inertia) (MIT) —
see `NOTICE`. Precognition and SSR are not implemented.

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

Standalone, configure it once and register the two exception handlers:

```python
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from simple_module_inertia import (
    Inertia,
    InertiaConfig,
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
app.add_exception_handler(
    InertiaVersionConflictException, inertia_version_conflict_exception_handler
)


@app.get("/")
async def home(inertia: Inertia = Depends(inertia_dep)):
    return await inertia.render("Home", {"greeting": "hello"})
```

The root template needs `{% inertia_head %}` in `<head>` and `{% inertia_body %}`
in `<body>`; the page object lands in `<div id="app" data-page="…">`.

## Prop resolution

Partial reloads accept dotted paths in `X-Inertia-Partial-Data` and
`X-Inertia-Partial-Except`, such as `auth.user`. Filtering traverses plain
Python dictionaries before running loaders. A callable, awaitable or `Prop`
resolves its children in full; `always()` also bypasses partial filters.
Merge and once metadata on partial reloads follows the selected paths.

`once(value, key=None, expires_at=None)` announces its cache key even when a
full Inertia visit omits its cached value. Partial reloads ignore
`X-Inertia-Except-Once-Props` and refresh requested once props.

`scroll(value, ..., wrapper="data", reset=False)` labels `<prop>.data` for
merging by default. Set `wrapper` to another dictionary path, or `None` to
merge a plain list at the prop root. The infinite-scroll merge-intent header
chooses append or prepend. The explicit `reset=True` argument or a prop path
in `X-Inertia-Reset` sets `scrollProps[path].reset` and suppresses merge labels.

`defer(value, group="default", rescue=False)` supports `rescue=True` for
loaders that may fail. A failed rescued loader logs its exception, leaves the
prop out of the response, and adds its path to `rescuedProps` so the client's
`<Deferred>` rescue slot can render. Other props still resolve; without
`rescue=True` the exception propagates. Deferred props are announced without
running their loaders on full visits. All wrappers compose through `Prop`,
for example `once(merge(defer(load_analytics, rescue=True)))`.
