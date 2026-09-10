# `simple_module_inertia` — a v3-capable Inertia adapter

**Date:** 2026-09-10 · **Status:** approved · **Supersedes:** the `fastapi-inertia>=1.0` dependency in `simple_module_hosting`

## Why

`@inertiajs/react` 3.x is current and 2.x is tagged `legacy`, but this project cannot move its
client because the server half of the protocol — `fastapi-inertia` (hxjo, MIT, 1.1.0, 824
lines) — implements only the v2 subset: plain props, `flash`, `deferred`, redirects and the
409 version check. It has none of `optional`/`always`/`merge`/`prepend`/`deepMerge`/`once`/
`scroll` props, `X-Inertia-Partial-Except`, `X-Inertia-Reset`, `encryptHistory`/`clearHistory`,
`preserveFragment`, or `X-Inertia-Redirect`. No v3-capable Python adapter exists.

We already fight upstream: `_inertia_setup.py` wraps its dependency twice
(`_inertia_json.py` so client-side visits encode props the same way full loads do;
`_inertia_url.py` so the page `url` is root-relative and `pushState` works behind a TLS
proxy — GH #223) and rewrites the Vite manifest because upstream keys it by
`"./main.tsx"` while Vite writes `"main.tsx"`. Owning the adapter puts those fixes where
they belong and unblocks the client upgrade.

## Decisions (approved)

| Question | Decision |
|---|---|
| Scope | Full v3 **page-object protocol**: every prop type, every partial-reload header, history flags, fragment-preserving redirects. **Excludes** Precognition and SSR. |
| Client | Migrating this repo's own client to `@inertiajs/react` v3 is part of this work — it is the end-to-end proof. Lands as a second PR. |
| Approach | Fork `fastapi-inertia` under MIT attribution and evolve it. Keep the `Inertia` / `InertiaResponse` / `InertiaConfig` names so call sites change only their import line. |
| Package name | `simple_module_inertia` at `framework/inertia/` — matches sibling naming. |
| Prop factory names | Mirror inertia-laravel (`optional`, `always`, `defer`, `merge`, `prepend`, `deep_merge`, `once`, `scroll`) so the official docs translate one-to-one. Upstream's `lazy()` stays as a deprecated alias of `optional()`. |

## 1. Package boundary

`framework/inertia/` → distribution `simple_module_inertia`, import `simple_module_inertia`,
lockstep-versioned with the other five framework packages (`bump_version.py` already walks
`framework/*/pyproject.toml`, so it needs no change).

- `simple_module_hosting` drops `fastapi-inertia>=1.0` and depends on
  `simple_module_inertia==<lockstep>` with a `[tool.uv.sources]` workspace entry.
- Module-facing contract is **unchanged**: `InertiaDep` (from
  `simple_module_hosting.inertia_deps`), `InertiaResponse`, `inertia.render(component, props)`,
  `inertia.share(**props)`. The 36 existing call sites change one import line:
  `from inertia import …` → `from simple_module_inertia import …`.
- Attribution: our `LICENSE` (MIT) plus a `NOTICE` file reproducing upstream's copyright and
  MIT text, as the MIT licence requires.
- Release: add `simple_module_inertia` to the `publish-pypi` matrix in
  `.github/workflows/release.yml`. **Operator action before the first tag:** register a PyPI
  *pending publisher* for `simple_module_inertia`, or that publish leg 403s and blocks the
  whole release.

## 2. Internal structure

Upstream's 477-line `inertia.py` exceeds the repo's 300-line cap, so the fork is split by
responsibility. Every file below has one job and is testable on its own.

| File | Responsibility |
|---|---|
| `config.py` | `InertiaConfig`. Upstream's fields, plus `version` accepting a `str` or a zero-arg callable (so the asset version can be computed from the Vite manifest hash at boot). |
| `props.py` | Prop wrappers and their factories: `OptionalProp`, `AlwaysProp`, `DeferredProp(group="default")`, `MergeProp(mode="append"\|"prepend"\|"deep", match_on=None)`, `OnceProp(key=None, expires_at=None)` — `key` defaults to the prop name; the page object reports `onceProps[key] = {"prop": name, "expiresAt": ms\|null}` — and `ScrollProp(page_name, current_page, previous_page, next_page, reset=False)`, reported under `scrollProps[name]` as `{pageName, currentPage, previousPage, nextPage, reset}` with `null` for an absent neighbour page. Wrappers compose — a deferred prop may also be mergeable, as the protocol allows. Each wraps a value, a callable, or an awaitable. |
| `request.py` | `InertiaRequest`, built from request headers only: `is_inertia`, `version`, `partial_component`, `partial_data`, `partial_except`, `reset`, `error_bag`, `merge_intent`, `except_once_props`, `is_prefetch`. A pure function of headers — no FastAPI objects. |
| `resolve.py` | The prop-resolution engine. Input: the raw props dict and an `InertiaRequest`. Output: `ResolvedProps` — resolved values plus page-object metadata (`deferredProps`, `mergeProps`, `prependProps`, `deepMergeProps`, `matchPropsOn`, `onceProps`, `scrollProps`). Implements the v3 rules in §3. |
| `page.py` | `PageObject` assembly and serialisation. Root-relative `url` (absorbs `_inertia_url`). Exactly one JSON encoder used by both the HTML and JSON branches (absorbs `_inertia_json`); it handles pydantic/SQLModel models, `datetime`, `UUID`, `Decimal`, enums. Conditional fields are emitted **only when set** — `encryptHistory`/`clearHistory`/`preserveFragment` only when `true`, the array/object metadata only when non-empty. |
| `response.py` | Turns a `PageObject` into an HTTP response: JSON (`X-Inertia: true`, `Vary: X-Inertia`) for Inertia requests, the Jinja root template otherwise; 409 + `X-Inertia-Location` (+ echoed `X-Inertia-Version`) on a GET version mismatch; 303 for redirects after POST/PUT/PATCH/DELETE; 409 + `X-Inertia-Redirect` for fragment-preserving redirects; `location()` for external redirects. |
| `inertia.py` | The request-scoped `Inertia` facade: `render`, `share`, `flash`, `back`, `redirect`, `location`, `encrypt_history`, `clear_history`. Thin — it delegates to `resolve`, `page`, `response`. |
| `manifest.py` | Reads the Vite manifest keyed exactly as Vite writes it and resolves the entry's JS + CSS. Hosting stops rewriting the file. |
| `errors.py` | Validation errors → session flash → the `errors` always-prop, scoped by error bag. Upstream's `exceptions.py`, renamed. |
| `templating.py` | The Jinja `inertia_head` / `inertia_body` extension. Upstream, substantively unchanged. |
| `deps.py` | `inertia_dependency_factory(config)` and the request → `Inertia` dependency. |

## 3. Prop-resolution rules (`resolve.py`)

These are the protocol's rules, stated so the conformance suite in §7 has something exact
to assert against.

- **Full visit** (no `X-Inertia-Partial-Component`, or it names a different component):
  regular, always and shared props resolve; `optional` and `deferred` are **skipped**;
  each deferred prop's key is reported under `deferredProps[group]`.
- **Partial reload** (`X-Inertia-Partial-Component` matches): only the keys in
  `X-Inertia-Partial-Data` resolve, minus any in `X-Inertia-Partial-Except`; `always` props
  resolve regardless; `optional` and `deferred` props resolve **when named**.
- `errors` is an always-prop — present in every response, `{}` when empty.
- **Once props**: skipped when their key appears in `X-Inertia-Except-Once-Props`; otherwise
  resolved and reported under `onceProps` with their `expiresAt` (ms) when set.
- **Merge props**: reported under `mergeProps` / `prependProps` / `deepMergeProps` by mode,
  with `matchPropsOn` entries as `"propPath.keyField"`. A key listed in `X-Inertia-Reset` is
  resolved but **not** reported as mergeable for that response, so the client replaces it.
- **Scroll props**: reported under `scrollProps` with their cursor metadata; the
  `X-Inertia-Infinite-Scroll-Merge-Intent` header selects append vs prepend for that response.
- Values that are callables are called; awaitables are awaited; nested containers are
  walked so a wrapper inside a dict or list still resolves.
- **Shared props** (`share()`) merge under the page's own props, page props winning on
  conflict; their top-level keys are reported under `sharedProps`.

## 4. Data flow

```
request headers ─► InertiaRequest ─► view: inertia.render(component, props)
                                            │
                          version mismatch? ─┴─► 409 + X-Inertia-Location   (before resolve)
                                            │
                                     resolve(props, req) ─► PageObject ─► response
                                                                  │
                                              X-Inertia? ─────────┼──► JSON
                                              otherwise ──────────┴──► root template (HTML)
```

Redirects (`redirect`, `back`, `location`) bypass the page pipeline entirely. Each stage is a
pure function of the previous one; that is what makes the stages unit-testable without a
server.

## 5. Backwards compatibility

- **A v2 client keeps working.** The four required page fields (`component`, `props`, `url`,
  `version`) are unchanged, and every v3 addition is conditional. A v2 client ignores fields it
  doesn't know. The package can therefore ship before the client migrates.
- **Existing call sites are unchanged** beyond the import line. `render(component, props)`
  keeps its signature and return type.
- **Hosting sheds three workarounds**: `_inertia_json.py`, `_inertia_url.py`, and the
  `_prod_manifest_path` re-keying in `_inertia_setup.py` are deleted; `setup_inertia` becomes
  a straight configuration function.
- `simple_module_test` fixtures are unchanged; the existing test suite must pass untouched.

## 6. Error handling

- **Validation errors**: 303 back to the referrer with errors flashed into the session,
  re-emitted on the next render under `errors`, scoped by `X-Inertia-Error-Bag`. This is
  today's `use_flash_errors=True` behaviour, kept.
- **Version mismatch**: 409 only on GET. The protocol has the client re-submit mutations
  itself, so POST/PUT/PATCH/DELETE proceed.
- **Misuse fails loudly at render**: a `scroll` or `once` prop missing its required key raises
  naming the prop; an unserialisable value raises naming the **prop path** (`props.user.avatar`)
  rather than a bare `TypeError`.
- **Unknown reset paths** in `X-Inertia-Reset` are ignored — the header is a client hint.

## 7. Testing

- **Unit, no server**: `props`, `request`, `resolve`, `page`, `response` each get their own
  test module. `resolve` gets a **table-driven protocol-conformance suite** — one row per
  scenario, asserting the exact resolved props and metadata:
  full visit · partial data · partial except · data + except · reset · once-except ·
  each merge mode with and without `matchPropsOn` · deferred groups · shared-vs-page
  precedence · callables and awaitables · nested wrappers. `response` covers: JSON vs HTML
  branch · `Vary` header · GET vs POST version mismatch · 303 after each mutating method ·
  fragment redirect · history flags emitted only when true · error bag scoping.
- **Integration**: the existing suite (2975 tests) passes untouched, proving the call-site
  contract held. `make doctor`'s SM003/SM004 page checks are unaffected.
- **Client** (PR 2): the 44 e2e tests run against the migrated v3 client, plus a `/qa` pass.
- **Lint**: every new file under the 300-line cap; `ty` clean; `ruff` clean.

## 8. Client migration (PR 2)

- `@inertiajs/react` `^2.3` → `^3.7` wherever it is pinned: root, `host/client_app`,
  `packages/ui` peer deps, every module's peer deps, both scaffold `package.json.tpl` files,
  and `_APP_NPM_DEPS` in `app_project.py`. `test_sm_new_flat_pins_inertia_react_to_v2` flips
  to assert `^3.`.
- The ~21 page layouts change from `Page.layout = (page) => <L>{page}</L>` to
  `Page.layout = [L]` — v3 requires the array form, and every layout here already takes
  `children`.
- `packages/ui/src/lib/spa-links.ts`: `router.on('invalid', …)` → `router.on('httpException', …)`.
- `host/templates/index.html` and the scaffold's `index.html`: `<title inertia="">` →
  `<title data-inertia="">`.
- `createInertiaApp` with our custom `resolve` is still valid; axios is no longer required.

## Out of scope

Precognition (live validation) and SSR. Both are separable subsystems; SSR in particular needs
a Node render server this project does not run. The package's structure leaves room for both
— `response.py` is where a Precognition branch would go, `templating.py` already carries
upstream's SSR head/body hooks — but neither is built here.
