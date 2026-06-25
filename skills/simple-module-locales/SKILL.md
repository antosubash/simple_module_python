---
name: simple-module-locales
description: Use when adding or debugging i18n in a simple_module_python module — declaring `locale_dirs()`, naming JSON files, picking a namespace, writing CLDR-pluralized keys, or fixing SM013–SM016. Triggers on "translations", "locales", "useT", "i18n", "missing locale", "non-string leaf", "first-render-locale freeze", or any edit under `<module>/locales/`.
---

# simple_module_python: locales (i18n)

## File layout

Each module ships JSON files under its `locales/` directory and points the framework at it from `ModuleBase.locale_dirs()`:

```
modules/orders/orders/
├── module.py
└── locales/
    ├── en.json
    └── es.json
```

```python
# orders/module.py
import importlib.resources
from pathlib import Path

class OrdersModule(ModuleBase):
    def locale_dirs(self) -> dict[str, Path]:
        # key = namespace, value = directory holding <lang>.json files
        return {"orders": Path(str(importlib.resources.files(__package__) / "locales"))}
```

The map's **key** is the i18n namespace (use the lowercase module package name); the **value** is the directory containing one JSON file per supported locale.

## Key-flattening + namespace prefix

Nested objects flatten with dotted keys, then the namespace prefixes the result:

```json
// orders/locales/en.json
{
  "browse": { "title": "Orders", "empty": "No orders yet." },
  "errors": { "not_found": "Order {id} not found" }
}
```

At runtime the keys become `orders.browse.title`, `orders.browse.empty`, `orders.errors.not_found`. Interpolation uses `{name}` placeholders, not `%(name)s` or `${name}`.

## CLDR pluralization

Use suffixes on the key — never branch in TypeScript:

```json
{
  "items_count_zero": "No items",
  "items_count_one": "{count} item",
  "items_count_other": "{count} items"
}
```

Supported suffixes: `_zero`, `_one`, `_two`, `_few`, `_many`, `_other`. **Only `_other` is required** — the rest are optional; the runtime falls back to `_other` for plural forms not declared. English needs `_one` and `_other`; Russian needs `_one`, `_few`, `_other`; Arabic uses all six.

## Frontend usage — `useT()`

```tsx
import { keys, useT } from '@simple-module-py/i18n';

export default function Browse({ orders }: Props) {
  const { t } = useT();
  return <h1>{t(keys.orders.browse.title)}</h1>;
  // or with interpolation
  // <p>{t('orders.errors.not_found', { id: 42 })}</p>
}
```

The shared prop `i18n` (set by `InertiaLayoutDataMiddleware`) carries the active locale + flattened bundle, so `useT()` doesn't fetch.

## The Zod-in-hook rule

**Translated Zod schemas must be constructed inside a hook**, never at module scope:

```tsx
// ❌ wrong — `t()` resolves once when the schema is built. The schema then
//   carries strings from whichever locale was active at first render —
//   forever, even after the user switches languages.
const schema = z.object({
  name: z.string().min(1, t('orders.validation.name_required')),
});

// ✅ right — schema is rebuilt per render, picking up the current locale.
export function useOrderSchema() {
  const { t } = useT();
  return z.object({
    name: z.string().min(1, t('orders.validation.name_required')),
  });
}
```

## Backend usage

Inject `TranslatorDep` (from `simple_module_hosting.i18n_deps`) into an endpoint to get a `Translator` bound to `request.state.locale` (set by `LocaleMiddleware`). Call `t.t(key, **params)` — same `{name}` placeholders, and pass `count=` for CLDR pluralization:

```python
from simple_module_hosting.i18n_deps import TranslatorDep

async def create(t: TranslatorDep):
    raise HTTPException(404, t.t("orders.errors.not_found", id=order_id))
```

Resolution falls back to the default locale, then to the bare key. Avoid hard-coding English in error responses that surface to users — pull the message through the locale system so other languages get it for free.

## Diagnostic codes

| Code | Level | Cause | Fix |
|---|---|---|---|
| **SM013** | WARNING | `locale_dirs()` declares a namespace, but a file is missing for one of `SM_I18N_SUPPORTED_LOCALES` | Create the file (even an empty `{}`) or trim the supported-locales list |
| **SM014** | WARNING | A non-default locale is missing keys that exist in the default (en) | Add the keys, or accept that the runtime falls back to default |
| **SM015** | WARNING | A non-default locale has keys **not** in the default | Either remove the dead keys or add them to the default file |
| **SM016** | ERROR | A locale JSON file is invalid or has non-string leaves | Fix the JSON. Only string leaves are allowed — interpolation is `{placeholder}` strings, not nested objects |

SM016 is fatal in production. SM013–SM015 are warnings, but they're the kind of warnings that turn into "Spanish users see English in production" if ignored.

## Pitfalls

- **Used a non-string leaf** (`"count": 5`, an array, or an object instead of a string with placeholders). SM016. Only string leaves; interpolate via `{name}` placeholders.
- **Skipped `locale_dirs()` even though `locales/` exists.** The framework only loads what's declared. The directory alone does nothing.
- **Used the module's PascalCase `meta.name` as the namespace key.** It must be the lowercase package name (typically the directory under `modules/`). Mixing cases breaks `keys.<namespace>.…` autocompletion in TS.
- **Constructed a translated Zod schema at module scope.** First-render-locale freeze — see the rule above. Always rebuild inside a hook.
- **Hand-edited the flattened key in JS instead of going through `keys.<namespace>.…`.** The `keys` proxy is type-safe; raw string keys silently rot when the JSON renames.
- **Pluralized with `if (n === 1)` in TSX.** Use CLDR suffixes — they handle locales English doesn't (Russian `_few`, Arabic `_zero`/`_two`/`_many`) without per-page branching.

## Related skills

- **simple-module-conventions** — the Zod-in-hook rule lives in the convention list
- **simple-module-doctor** — full reference for `SM013`–`SM016`
- **simple-module-inertia-pages** — how `i18n` lands in shared props
