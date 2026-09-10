# simple_module_inertia

Inertia.js **v3** server adapter for FastAPI. This is the protocol half of a
simple_module app's React frontend: it turns `inertia.render("Users/Index", props)`
into either the JSON page object an Inertia visit expects or the HTML document a
full page load expects, and implements every v3 prop type (`optional`, `always`,
`defer`, `merge`, `prepend`, `deep_merge`, `once`, `scroll`).

Forked from [fastapi-inertia](https://github.com/hxjo/fastapi-inertia) (MIT) —
see `NOTICE`. Precognition and SSR are not implemented.

Used by `simple_module_hosting`; module authors reach it through
`simple_module_hosting.inertia_deps.InertiaDep` and import `InertiaResponse`
and the prop factories from `simple_module_inertia`.
