# i18n Localization — Design

**Date:** 2026-04-15
**Status:** Approved for planning
**Scope:** Unified frontend + backend localization system driven by per-module JSON files, with type-safe key access on the frontend.

## Summary

Add end-to-end localization to the framework: React UI strings, FastAPI user-facing messages, email/flash content, and page titles all resolve through a shared, module-contributed JSON registry. Frontend uses `i18next` + `react-i18next`; backend uses Python `Babel` for CLDR plural rules. Locale is selected via a cookie that an authenticated or anonymous user sets through a switcher in the layout. Type safety: unknown translation keys are a TypeScript compile error; params are untyped.

## Goals

- Single source of truth per module per locale — one JSON file, read by both Python and TypeScript.
- Per-module contribution that matches the existing modular-monolith pattern (mirrors `template_dirs()`, `static_mounts()`, permission/menu registration).
- Compile-time detection of unknown translation keys on the frontend.
- Correct pluralization across locales via CLDR rules (e.g., Russian's four plural forms).
- Works for pip-installed module wheels, not just the monorepo layout.
- A newly scaffolded module is localizable from the first `make new-module`.

## Non-Goals

- Locale-aware date/number/currency formatting (Babel can, but it's a separate concern with its own UX questions; design so it can slot in later).
- Translation management tooling integration (Crowdin, Lokalise, Phrase). JSON files are edited by hand.
- RTL layout support.
- Per-user locale preference stored on the user model (cookie-based selection works uniformly for anonymous + authenticated; layering user-preference storage comes later without breaking this design).
- Machine-translation pipeline at runtime or in CI.
- Lazy-loading locales on the frontend (one locale's messages ship per request via Inertia shared props; payload is small).

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Frontend + backend unified | Single source of truth; one translator rhythm for module authors. |
| File location | Per-module + host + UI package | Matches existing per-module template/static pattern. |
| Locale selection | Cookie, set by a switcher UI | Works for anonymous + authenticated users uniformly; no DB changes. |
| Type safety | Key existence only (level A) | Simple codegen; params as `Record<string, unknown>`. |
| Pluralization | Simple plurals (`_one`/`_other`/...), i18next-style | Covers real-world 95% case. |
| Frontend library | `i18next` + `react-i18next` | Mature, first-class TS augmentation for typed keys. |
| Backend library | `Babel` | CLDR plural rules; future-proofs date/number formatting. |
| JSON split | One combined file per locale per module (not split client/server) | Minor over-ship to client is worth the simpler mental model. |
| Frontend tests | Introduce Vitest | Project has no existing JS test runner; this feature justifies adding one. |

## Architecture

### File Layout

```
modules/<module>/<module>/
  locales/
    en.json
    es.json
    <other>.json

host/
  locales/
    en.json           # landing page, error page, switcher labels
    es.json

packages/ui/
  locales/
    en.json           # PageShell, ErrorBoundary, Empty, etc.
    es.json

packages/i18n/        # NEW workspace package
  package.json
  tsconfig.json
  src/
    index.ts          # configureI18n(), useT(), t() re-exports
    *.test.ts

host/client_app/      # host-level host-app additions
  i18n.ts             # NEW: initial-props wiring for configureI18n
  i18n-types.ts       # NEW: i18next module augmentation (app-level)
  generated-resources.ts  # NEW (generated): default-locale key shape

framework/core/simple_module_core/
  i18n.py             # NEW: I18nRegistry, Translator

framework/hosting/simple_module_hosting/
  middleware.py       # extended: add LocaleMiddleware
  settings.py         # extended: SM_I18N_* settings
```

### Module Contribution

`ModuleBase` gains a new optional method, returning a `{namespace: directory}` mapping:

```python
def locale_dirs(self) -> dict[str, Path]:
    """Return {namespace: directory} mapping for locale JSON files.

    Default returns an empty dict. Override to contribute a module's locales:

        return {"products": importlib.resources.files(__package__) / "locales"}

    The namespace becomes the key prefix in the merged registry. A file
    `locales/en.json` containing `{"browse": {"title": "Products"}}` becomes
    the key `products.browse.title` at runtime.
    """
    return {}
```

Returning a dict (not a list) lets a module pick its own namespace explicitly. Convention: use the module's lowercase name. There is no framework-imposed default — the namespace is always whatever the module returns.

### Namespacing

All keys live under a module-provided namespace. The host contributes `host.*`, the shared UI package contributes `ui.*`, each module contributes `<module>.*`. Namespaces prevent collisions between modules developed independently.

### JSON Shape

Module JSON files are nested for human readability; the registry flattens to dotted keys at load time.

Example `modules/products/products/locales/en.json`:

```json
{
  "browse": {
    "title": "Products",
    "search_placeholder": "Search products...",
    "count_one": "{count} product",
    "count_other": "{count} products",
    "empty_title": "No products yet",
    "empty_description": "Get started by creating your first product."
  },
  "actions": {
    "delete_confirm_title": "Delete \"{name}\"?",
    "delete_confirm_body": "This action cannot be undone. This will permanently delete the product from the catalog."
  }
}
```

Interpolation placeholders use `{name}` syntax (consistent between frontend and backend). Plural variants use suffixes `_zero`/`_one`/`_two`/`_few`/`_many`/`_other`, matching CLDR categories; only `_other` is required for every pluralized key.

## Backend

### I18nRegistry

```python
# framework/core/simple_module_core/i18n.py

class I18nRegistry:
    """Merged view of all module locale JSON files, keyed by locale."""

    def __init__(self, default_locale: str, supported_locales: list[str]): ...

    def add_source(self, namespace: str, locale_dir: Path) -> None:
        """Queue a module's locale directory for loading under a namespace."""

    def load(self) -> None:
        """Read and flatten all registered JSON files. Called once at boot.

        Logs warnings for missing locale files. Raises in production if a
        supported locale has no files anywhere (via diagnostics, not here).
        """

    def available_locales(self) -> list[str]:
        """Locales that have at least one loaded JSON file."""

    def messages(self, locale: str) -> dict[str, str]:
        """Flat dotted-key map for the given locale."""
```

Flattening: `{"browse": {"title": "X"}}` under namespace `products` becomes `{"products.browse.title": "X"}`.

### Translator

```python
class Translator:
    def __init__(
        self,
        registry: I18nRegistry,
        locale: str,
        default_locale: str,
    ): ...

    def t(self, key: str, **params: Any) -> str:
        """Translate a key with optional interpolation and plural resolution.

        1. If `count` in params and `key` has `_<plural>` variants, resolve
           the plural form via Babel's PluralRule for the current locale.
        2. Look up the (possibly-pluralized) key in the requested locale.
        3. Fall back to the default locale.
        4. Fall back to returning the key itself (with a dev-mode log warning).
        5. Interpolate `{name}`-style placeholders via str.format_map.
        """
```

The plural resolver uses `babel.plural.PluralRule`:

```python
from babel.plural import PluralRule
from babel import Locale

rule = Locale.parse(locale).plural_form  # Callable[[int|float], str]
category = rule(params["count"])          # "zero" | "one" | ... | "other"
pluralized_key = f"{key}_{category}"
```

### Request Pipeline

1. **`LocaleMiddleware`** — runs very early in the stack, before `InertiaLayoutData`. Resolution order:
   1. Cookie named by `SM_I18N_COOKIE_NAME` (default `locale`), validated against `registry.available_locales()`.
   2. `Accept-Language` header, negotiated against supported locales (use `babel.localedata` or a simple longest-prefix match — implementation detail for the plan).
   3. `SM_I18N_DEFAULT_LOCALE`.

   Sets `request.state.locale`.

2. **`TranslatorDep`** — a FastAPI dependency returning a `Translator` bound to `request.state.locale`:

   ```python
   async def get_translator(request: Request) -> Translator: ...

   TranslatorDep = Annotated[Translator, Depends(get_translator)]
   ```

   Endpoints use it directly:
   ```python
   async def login(t: TranslatorDep, ...) -> ...:
       flash(request, t.t("auth.login.failed"))
   ```

3. **Inertia shared props** — `InertiaLayoutData` middleware appends:
   ```python
   {
       "locale": request.state.locale,
       "supportedLocales": registry.available_locales(),
       "messages": registry.messages(request.state.locale),
   }
   ```
   to the shared props dict. Messages are the pre-flattened dict for the active locale only.

### Switcher Endpoint

`POST /i18n/set-locale` in `host/routes.py`:

- Body: form-encoded `locale=<code>`.
- Validates against `registry.available_locales()`; rejects with 422 otherwise.
- Sets the cookie: `HttpOnly=false` (the frontend may need to read it for optimistic rendering), `SameSite=Lax`, `Path=/`, `Max-Age=31536000` (1 year). Long-lived is the right default — users expect their language choice to survive browser restarts.
- 303-redirects to the `Referer` header, falling back to `/`.

### Settings Additions

```python
# In Settings (pydantic-settings model):
i18n_default_locale: str = "en"
i18n_supported_locales: list[str] = ["en"]   # comma-separated in env
i18n_cookie_name: str = "locale"
```

Environment variable examples:
```
SM_I18N_DEFAULT_LOCALE=en
SM_I18N_SUPPORTED_LOCALES=en,es,de
SM_I18N_COOKIE_NAME=locale
```

### Boot Sequence Integration

`locale_dirs()` is pure metadata (like `template_dirs()`), not a registration hook. The host's boot sequence iterates each module once, calls `module.locale_dirs()`, and feeds the `{namespace: path}` pairs into `registry.add_source()`. After all modules are visited, `registry.load()` is called to read and flatten every JSON file. This happens in Phase 2 (App creation) alongside other metadata gathering, before Phase 4's registration hooks — because Phase 4 hooks (e.g., endpoints wired up via `register_routes`) may depend on `TranslatorDep` resolving against a populated registry.

## Frontend

### `packages/i18n`

New workspace package, depends on `i18next` and `react-i18next`, consumed as `@simple-module-py/i18n`.

```ts
// packages/i18n/src/index.ts
export function configureI18n(opts: {
  locale: string;
  messages: Record<string, string>;
}): void;

export function updateI18n(opts: {
  locale: string;
  messages: Record<string, string>;
}): void;  // for locale changes after initial boot

export { useTranslation as useT } from 'react-i18next';
export { t } from 'i18next';  // for non-hook contexts
```

`configureI18n` is called once at app boot with the `{locale, messages}` Inertia shared props, before rendering the React tree. `updateI18n` is called when Inertia navigation brings a new locale (e.g., after the switcher POST).

### Resource Delivery & Aggregation

**Runtime data flow:** The frontend trusts Inertia shared props as the sole source of translation data at runtime. The backend's `I18nRegistry.messages(locale)` is serialized into `props.messages` on every Inertia response; `configureI18n` passes that dict directly to i18next. No frontend glob of locale JSON runs in production — this keeps the JS bundle small.

**Build-time typing:** Type generation still needs to know the full key set of the default locale. The Python host emits `host/client_app/generated-resources.ts` at boot (alongside the existing `modules.generated.ts`), flattening the default locale's merged JSON into an object literal with empty-string values. This file is the shape fed into i18next's TypeScript module augmentation (see "Type Safety" below). It is imported only by `types.ts` for type inference; tree-shaking excludes it from the runtime bundle.

### Type Safety (Level A)

i18next supports TypeScript module augmentation to make `t()` strongly typed over key existence. The augmentation lives in `host/client_app/` (consumer), not in `packages/i18n/` (provider) — because the key set depends on which modules are installed, so it's an app-level concern, not a library-level one. `packages/i18n` exports `useT`/`configureI18n` without any key typing; `host/client_app/i18n-types.ts` augments `'i18next'` using a host-local generated file:

```ts
// host/client_app/i18n-types.ts
import 'i18next';
import type resources from './generated-resources';

declare module 'i18next' {
  interface CustomTypeOptions {
    resources: typeof resources;
  }
}
```

`host/client_app/generated-resources.ts` is emitted by the Python host at boot, alongside `modules.generated.ts`. Shape:

```ts
// host/client_app/generated-resources.ts (generated — do not edit)
export default {
  translation: {
    'host.landing.title': '',
    'products.browse.title': '',
    'products.browse.count_one': '',
    'products.browse.count_other': '',
    // ... all keys from the default-locale merged JSON, values are empty strings
    //     (only the key shape matters for typing; values are never read)
  },
} as const;
```

`i18n-types.ts` is imported once from `main.tsx` so its augmentation takes effect app-wide. Effect: `t('products.browse.title')` compiles; `t('products.browse.titel')` is a type error. Params remain `Record<string, unknown>` (level A).

### React Integration

`host/client_app/app.tsx` initializes i18next before rendering:

```tsx
import { configureI18n } from '@simple-module-py/i18n';

createInertiaApp({
  resolve: async (name) => resolvePage(name),
  setup({ el, App, props }) {
    // Initial props include locale + messages from the first page response.
    const { locale, messages } = props.initialPage.props as any;
    configureI18n({ locale, messages });
    // ... existing setup
  },
});
```

Subsequent Inertia visits bring fresh `{locale, messages}`; a `router.on('success')` hook calls `updateI18n` when the incoming locale differs from the current one.

Page-level usage:

```tsx
import { useT } from '@simple-module-py/i18n';

function Browse() {
  const { t } = useT();
  return <h1>{t('products.browse.title')}</h1>;
}
```

### Locale Switcher Component

`packages/ui/src/components/LocaleSwitcher.tsx` — shadcn `DropdownMenu` + form submit:

- Props: `{ current: string; supported: string[]; localeLabels?: Record<string, string> }`.
- Reads `current`/`supported` from Inertia shared props via `usePage()` if no explicit props passed.
- Dropdown items post to `/i18n/set-locale` via a hidden form with CSRF handled by the existing session middleware.
- Rendered in `AuthenticatedLayout` (sidebar/header) and `PublicLayout` (header right).

Human-readable locale labels (`"English"`, `"Español"`) are NOT generated from JSON keys — they live in a small static map in the component. This is intentional: the user picks a language *before* they can read the current UI language, so labels should be in each locale's own language, not the current UI language.

### Validation Messages

Form validation in module pages (e.g., `modules/products/products/pages/validation.ts`) currently contains hardcoded Zod messages. Pattern for localization:

```ts
import { useT } from '@simple-module-py/i18n';
import { z } from 'zod';

export function useProductSchema() {
  const { t } = useT();
  return z.object({
    name: z.string().min(1, t('products.validation.name_required')),
    price: z.coerce.number().positive(t('products.validation.price_positive')),
  });
}
```

Validation messages must be created inside a hook, not at module top-level, so they resolve against the current locale. Documented in `framework-conventions.md`.

## Module Authoring Experience

### Scaffolder Updates

`scripts/new_module.py` (`make new-module name=orders`) additionally creates:

```
modules/orders/orders/locales/
  en.json       # pre-populated with keys matching scaffolded pages
```

Scaffolded `en.json` includes every string used by the scaffolded `Browse.tsx`, `Create.tsx`, `Edit.tsx` — page titles, button labels, empty states, toast messages, alert-dialog copy, plus any server-side flash messages from scaffolded endpoints. No hardcoded strings in scaffolded templates; everything uses `t()` / `TranslatorDep`.

Scaffolded `module.py` includes:

```python
def locale_dirs(self) -> dict[str, Path]:
    from importlib.resources import files
    return {"orders": files(__package__) / "locales"}
```

### `framework-conventions.md` Additions

A new "Internationalization" section documenting:

- Where translation files live per module.
- Key naming convention: `<namespace>.<area>.<string>`, snake_case leaves.
- Interpolation: `{name}` placeholders.
- Pluralization: CLDR-suffixed keys; pass `count` param to `t()`.
- Host/UI strings live in `host/locales/` and `packages/ui/locales/`, namespaced `host.*` / `ui.*`.
- Validation messages must be constructed inside hooks.
- `make doctor` enforces key parity across locales.

## Diagnostics

New `I18nDiagnostic` in `framework/core/simple_module_core/diagnostics/`:

- Every source declared in `add_source()` has at least `<default_locale>.json`.
- For each module, every `<locale>.json` that exists has the same top-level key set as the default-locale file. Missing keys in non-default files are warnings; extra keys in non-default files are warnings.
- All JSON files parse cleanly (errors, not warnings).
- JSON files are structurally valid (nested dicts + leaf strings only; no arrays, no numbers).

Warnings in dev; errors fail boot in production (matches existing diagnostic behavior).

Invocation via `make doctor` — existing command, new sub-check.

## Migration of Existing Strings

In-scope as part of this work:

- Extract hardcoded strings from `modules/auth/`, `modules/dashboard/`, `modules/products/`, `host/`, and `packages/ui/` into their respective `locales/en.json`.
- Ship `es.json` for every source as a second locale — Spanish translations may be machine-generated for the initial commit. Purpose is to exercise the pipeline end-to-end so `make doctor` has something to diff against and the switcher has a second option to choose.
- Update scaffolded templates in `scripts/new_module.py` to emit `t()`-using versions.

## Testing Strategy

### Backend (pytest)

Lives in `framework/core/tests/test_i18n.py` and `framework/hosting/tests/test_locale_middleware.py`.

- `I18nRegistry`: flattening nested JSON, namespace prefixing, locale lookup, missing-locale handling, invalid-JSON handling.
- `Translator.t()`: key lookup, fallback to default locale, fallback to key when missing everywhere, `{name}` interpolation, plural resolution for `en` (`_one`/`_other`) and `ru` (`_one`/`_few`/`_many`/`_other`) — verifying Babel drives the resolution.
- `LocaleMiddleware`: cookie → `Accept-Language` → default fallback chain; invalid cookie values dropped; `request.state.locale` populated before Inertia middleware.
- Diagnostics: missing-locale-file detection, missing-key detection, malformed JSON detection.

Integration tests:

- `POST /i18n/set-locale` sets the cookie, rejects unsupported locales (422), 303-redirects.
- An endpoint using `TranslatorDep` returns localized flash messages when the cookie is `es`.
- Inertia shared props include the correct `{locale, messages}` for the request's locale.

Uses existing `conftest.py` fixtures (`db_session`, `authenticated_client`).

### Frontend (Vitest — newly introduced)

Root `package.json` gains `vitest`, `@testing-library/react`, `@testing-library/jest-dom` as dev deps. Root `test` script runs `vitest run`. `Makefile` gains a `test-js` target; `make test` runs both `pytest` and `test-js`.

Initial coverage:

- `packages/i18n/src/*.test.ts` — `configureI18n()` merges resources into the expected shape; `t()` returns the right string for a known key; unknown key falls back to the key itself; plural resolution picks `_one` vs `_other` for English.
- `packages/ui/src/components/LocaleSwitcher.test.tsx` — renders supported locales from props, submits form on selection, marks the active locale.

`vitest.config.ts` in `host/client_app/` reuses Vite's resolve/plugin config.

### End-to-End Smoke (manual checklist in acceptance criteria)

1. `make dev` → land on `/` in English.
2. Click switcher → pick Spanish → page re-renders in Spanish.
3. Navigate to `/products` → module-scoped strings are Spanish.
4. Refresh → still Spanish (cookie persisted).
5. `make doctor` → no i18n warnings.
6. `make lint` passes (including generated `.d.ts` typing).
7. `make test` (both pytest + Vitest) passes.

## Acceptance Criteria

- [ ] All of `modules/auth`, `modules/dashboard`, `modules/products`, `host/`, `packages/ui/` have their user-facing strings extracted to `locales/en.json` and `locales/es.json`.
- [ ] `t('products.browse.title')` works in React; unknown keys are a TS compile error.
- [ ] `t.t("auth.login.failed")` works in FastAPI endpoints via `TranslatorDep`.
- [ ] `POST /i18n/set-locale` with `locale=es` sets the cookie and subsequent page loads render Spanish.
- [ ] Inertia shared props include `{locale, supportedLocales, messages}` on every page.
- [ ] `make doctor` reports no i18n issues against the shipped modules.
- [ ] `make test` passes (pytest + Vitest).
- [ ] `make new-module name=orders` produces a module whose pages use `t()` and whose `locales/en.json` matches the scaffolded template strings; the module is immediately localizable.
- [ ] `framework-conventions.md` has an Internationalization section documenting the conventions.

## Open Questions

None — all raised during brainstorming were resolved before spec was written.

## References

- `docs/framework-conventions.md` — module authoring invariants this design extends.
- `docs/superpowers/specs/2026-04-13-module-lifecycle-hooks-design.md` — phased boot sequence where `locale_dirs()` integrates.
- `framework/core/simple_module_core/module.py:132` — `template_dirs()` precedent for `locale_dirs()`.
- `framework/hosting/simple_module_hosting/inertia_deps.py` — `InertiaDep` precedent for `TranslatorDep`.
- `host/client_app/pages.ts` — `modules.generated.ts` glob pattern that locale aggregation mirrors.
