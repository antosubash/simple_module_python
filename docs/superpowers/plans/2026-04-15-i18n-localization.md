# i18n Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unified frontend + backend localization, driven by per-module JSON files, with type-safe key access on the frontend and CLDR-correct plurals on the backend.

**Architecture:** Module authors contribute `locales/<lang>.json` files alongside their Python package. At boot, the host merges them into an `I18nRegistry` (backend) and emits a `generated-resources.ts` file (frontend typing). A cookie-based `LocaleMiddleware` resolves the active locale per request and ships the active-locale messages as Inertia shared props. Frontend uses `i18next` + `react-i18next` with TypeScript module augmentation for compile-time key checking. Backend exposes a `TranslatorDep` for endpoint use, with plural resolution via `babel.plural.PluralRule`.

**Tech Stack:** Python 3.12, FastAPI, `babel>=2.14`, `i18next`, `react-i18next`, Vite, Vitest, TypeScript 5.7.

**Spec reference:** [docs/superpowers/specs/2026-04-15-i18n-localization-design.md](../specs/2026-04-15-i18n-localization-design.md)

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `framework/core/simple_module_core/i18n.py` | `I18nRegistry`, `Translator`, JSON flattening, plural resolution |
| `framework/core/tests/test_i18n.py` | Unit tests for registry + translator + plurals |
| `framework/core/simple_module_core/diagnostics/_i18n.py` | `I18nDiagnostics` class |
| `framework/hosting/simple_module_hosting/i18n_middleware.py` | `LocaleMiddleware` (cookie → Accept-Language → default) |
| `framework/hosting/simple_module_hosting/i18n_deps.py` | `TranslatorDep` FastAPI dependency |
| `framework/hosting/simple_module_hosting/i18n_manifest.py` | Emit `generated-resources.ts` for frontend type inference |
| `framework/hosting/tests/test_locale_middleware.py` | Middleware unit tests |
| `framework/hosting/tests/test_translator_dep.py` | Dependency integration test |
| `framework/hosting/tests/test_i18n_manifest.py` | Test `generated-resources.ts` emission |
| `host/routes_i18n.py` | `POST /i18n/set-locale` switcher endpoint |
| `host/locales/en.json` | Host-level strings (landing, error page, switcher labels) |
| `host/locales/es.json` | Spanish translations for the above |
| `host/client_app/i18n.ts` | Initial `configureI18n` + `router.on('success')` updater |
| `host/client_app/i18n-types.ts` | i18next module augmentation |
| `host/client_app/generated-resources.ts` | GENERATED — default-locale key shape |
| `packages/ui/locales/en.json` | Shared UI strings (`ui.*`) |
| `packages/ui/locales/es.json` | Spanish translations |
| `packages/ui/src/components/LocaleSwitcher.tsx` | Dropdown switcher component |
| `packages/ui/src/components/LocaleSwitcher.test.tsx` | Vitest unit test |
| `packages/i18n/package.json` | Workspace package descriptor |
| `packages/i18n/tsconfig.json` | TS config |
| `packages/i18n/src/index.ts` | `configureI18n`, `updateI18n`, `useT`, `t` re-exports |
| `packages/i18n/src/configure.test.ts` | Vitest unit tests |
| `modules/<each>/<each>/locales/en.json` | Each of `auth`, `dashboard`, `products` — extracted strings |
| `modules/<each>/<each>/locales/es.json` | Spanish counterparts |
| `vitest.config.ts` (root) | Vitest project config |
| `vitest.setup.ts` (root) | Vitest setup (jest-dom matchers) |

### Modified files

| File | Change |
|---|---|
| `framework/core/simple_module_core/module.py` | Add `locale_dirs()` method to `ModuleBase` |
| `framework/core/simple_module_core/__init__.py` | Export `I18nRegistry`, `Translator` |
| `framework/core/simple_module_core/diagnostics/__init__.py` | Export `I18nDiagnostics` |
| `framework/core/simple_module_core/diagnostics/_runner.py` | Run i18n diagnostics |
| `framework/core/pyproject.toml` | Add `babel>=2.14` dep |
| `framework/hosting/simple_module_hosting/settings.py` | Add `i18n_default_locale`, `i18n_supported_locales`, `i18n_cookie_name` |
| `framework/hosting/simple_module_hosting/app_builder.py` | Wire i18n registry + middleware + manifest emission |
| `framework/hosting/simple_module_hosting/middleware.py` | (No change — new middleware is its own file) |
| `host/main.py` | (No change — goes through `create_app`) |
| `host/routes.py` | (No change — switcher lives in new file `routes_i18n.py`) |
| `host/client_app/main.tsx` | Import `i18n-types.ts` to activate augmentation |
| `host/client_app/app.tsx` | Call `configureI18n` at boot; wire `updateI18n` on navigate |
| `host/client_app/package.json` | Add `i18next`, `react-i18next`, `@simple-module/i18n` deps |
| `packages/ui/package.json` | Add `@simple-module/i18n` dep |
| `packages/ui/src/layouts/AuthenticatedLayout.tsx` | Mount `<LocaleSwitcher />` |
| `packages/ui/src/layouts/PublicLayout.tsx` | Mount `<LocaleSwitcher />` |
| `package.json` (root) | Add `vitest`, `@testing-library/*`, `@vitest/ui` devDeps; add `test` script |
| `Makefile` | Add `test-js` target; fold into `make test` |
| `modules/auth/auth/module.py` | Add `locale_dirs()` |
| `modules/auth/auth/endpoints/*.py` | Swap hardcoded strings for `TranslatorDep` |
| `modules/dashboard/dashboard/module.py` | Add `locale_dirs()` |
| `modules/dashboard/dashboard/pages/*.tsx` | Swap strings for `useT()` |
| `modules/products/products/module.py` | Add `locale_dirs()` |
| `modules/products/products/pages/Browse.tsx` | Swap strings for `useT()` |
| `modules/products/products/pages/Create.tsx` | Swap strings for `useT()` |
| `modules/products/products/pages/Edit.tsx` | Swap strings for `useT()` |
| `modules/products/products/pages/validation.ts` | Export `useProductSchema()` hook |
| `host/client_app/pages/Landing.tsx` | Swap strings for `useT()` |
| `host/client_app/pages/Error.tsx` | Swap strings for `useT()` |
| `scripts/new_module.py` | Create `locales/en.json`; update `locale_dirs()` in generated `module.py` |
| `scripts/_templates_py.py` | Update `module_py` template to include `locale_dirs()` |
| `scripts/_templates_tsx.py` | Update Browse/Create/Edit templates to use `useT()` |
| `docs/framework-conventions.md` | Add Internationalization section |
| `README.md` | Add "Internationalization" bullet to Architecture section |

---

## Build Sequence Overview

- **Tasks 1–6:** Backend core (registry, translator, plurals, middleware, dep) — no UI depends on this yet.
- **Tasks 7–10:** Manifest emission + frontend types + `packages/i18n`.
- **Tasks 11–13:** Switcher endpoint + React wiring + switcher component.
- **Tasks 14–15:** Vitest setup + frontend tests.
- **Task 16:** Diagnostics.
- **Task 17:** Extract strings from `packages/ui`.
- **Tasks 18–20:** Extract strings from each module (auth, dashboard, products) + host.
- **Task 21:** Scaffolder updates.
- **Task 22:** Docs + README.
- **Task 23:** End-to-end smoke verification.

---

## Task 1: `I18nRegistry` — load and flatten JSON files

**Files:**
- Create: `framework/core/simple_module_core/i18n.py`
- Create: `framework/core/tests/test_i18n.py`
- Modify: `framework/core/pyproject.toml` (add `babel`)

**Context:** The registry is pure Python data-structure code with no FastAPI/Babel coupling yet. It loads JSON from disk, flattens nested dicts to dotted keys, and stores per-locale maps. Plural resolution comes in Task 3.

- [ ] **Step 1: Add `babel` dependency to core**

Edit `framework/core/pyproject.toml` — add `"babel>=2.14"` to the `dependencies` list:

```toml
dependencies = [
    "babel>=2.14",
    "fastapi>=0.115",
    "packaging>=23.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "pyee>=12.0",
]
```

Then run:

```bash
uv sync --all-packages
```

- [ ] **Step 2: Write failing test for JSON flattening**

Create `framework/core/tests/test_i18n.py`:

```python
"""Tests for I18nRegistry, Translator, and plural resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_module_core.i18n import I18nRegistry, flatten_messages


class TestFlattenMessages:
    def test_flattens_nested_dict_with_dotted_keys(self) -> None:
        nested = {"browse": {"title": "Products", "count_one": "{count} product"}}
        flat = flatten_messages(nested)
        assert flat == {
            "browse.title": "Products",
            "browse.count_one": "{count} product",
        }

    def test_flattens_deeply_nested(self) -> None:
        nested = {"a": {"b": {"c": "hello"}}}
        assert flatten_messages(nested) == {"a.b.c": "hello"}

    def test_rejects_non_string_leaves(self) -> None:
        nested = {"count": 42}
        with pytest.raises(ValueError, match="must be string"):
            flatten_messages(nested)

    def test_rejects_list_values(self) -> None:
        nested = {"items": ["a", "b"]}
        with pytest.raises(ValueError, match="must be string"):
            flatten_messages(nested)

    def test_empty_dict_returns_empty(self) -> None:
        assert flatten_messages({}) == {}
```

- [ ] **Step 3: Run the test and verify it fails**

```bash
cd framework/core && uv run pytest tests/test_i18n.py::TestFlattenMessages -v
```

Expected: `ModuleNotFoundError: No module named 'simple_module_core.i18n'`.

- [ ] **Step 4: Implement `flatten_messages`**

Create `framework/core/simple_module_core/i18n.py`:

```python
"""Internationalization registry and translator."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def flatten_messages(
    nested: dict[str, Any],
    *,
    prefix: str = "",
) -> dict[str, str]:
    """Flatten a nested dict of string leaves to dotted keys.

    {"browse": {"title": "X"}} -> {"browse.title": "X"}

    Raises ValueError if any leaf is not a string.
    """
    out: dict[str, str] = {}
    for key, value in nested.items():
        composed = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten_messages(value, prefix=composed))
        elif isinstance(value, str):
            out[composed] = value
        else:
            raise ValueError(
                f"Locale value at '{composed}' must be string or nested dict, "
                f"got {type(value).__name__}"
            )
    return out
```

- [ ] **Step 5: Verify flattening tests pass**

```bash
cd framework/core && uv run pytest tests/test_i18n.py::TestFlattenMessages -v
```

Expected: 5 passed.

- [ ] **Step 6: Write failing test for `I18nRegistry` loading**

Append to `framework/core/tests/test_i18n.py`:

```python
class TestI18nRegistry:
    def _write_locale(self, dir_: Path, lang: str, data: dict) -> None:
        dir_.mkdir(parents=True, exist_ok=True)
        (dir_ / f"{lang}.json").write_text(json.dumps(data))

    def test_loads_single_namespace(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "products", "en", {"browse": {"title": "Products"}})
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("products", tmp_path / "products")
        reg.load()
        assert reg.messages("en") == {"products.browse.title": "Products"}

    def test_merges_multiple_namespaces(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "p", "en", {"title": "Products"})
        self._write_locale(tmp_path / "a", "en", {"title": "Auth"})
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("products", tmp_path / "p")
        reg.add_source("auth", tmp_path / "a")
        reg.load()
        assert reg.messages("en") == {"products.title": "Products", "auth.title": "Auth"}

    def test_available_locales_reports_loaded(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "h", "en", {"k": "v"})
        self._write_locale(tmp_path / "h", "es", {"k": "v_es"})
        reg = I18nRegistry(default_locale="en", supported_locales=["en", "es", "de"])
        reg.add_source("host", tmp_path / "h")
        reg.load()
        assert sorted(reg.available_locales()) == ["en", "es"]

    def test_missing_locale_file_is_warning_not_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._write_locale(tmp_path / "h", "en", {"k": "v"})
        # No es.json
        reg = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
        reg.add_source("host", tmp_path / "h")
        with caplog.at_level("WARNING"):
            reg.load()
        assert "missing locale file" in caplog.text.lower()
        assert reg.messages("es") == {}

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        d = tmp_path / "h"
        d.mkdir()
        (d / "en.json").write_text("{not valid json")
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("host", d)
        with pytest.raises(ValueError, match="invalid JSON"):
            reg.load()

    def test_messages_unknown_locale_returns_empty(self, tmp_path: Path) -> None:
        self._write_locale(tmp_path / "h", "en", {"k": "v"})
        reg = I18nRegistry(default_locale="en", supported_locales=["en"])
        reg.add_source("host", tmp_path / "h")
        reg.load()
        assert reg.messages("fr") == {}
```

- [ ] **Step 7: Run and verify failure**

```bash
cd framework/core && uv run pytest tests/test_i18n.py::TestI18nRegistry -v
```

Expected: `ImportError` on `I18nRegistry`.

- [ ] **Step 8: Implement `I18nRegistry`**

Append to `framework/core/simple_module_core/i18n.py`:

```python
class I18nRegistry:
    """Merged view of all module locale JSON files, keyed by locale.

    Usage::

        registry = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
        registry.add_source("products", Path("modules/products/products/locales"))
        registry.load()
        registry.messages("en")  # {"products.browse.title": "Products", ...}
    """

    def __init__(self, default_locale: str, supported_locales: list[str]) -> None:
        self.default_locale = default_locale
        self.supported_locales = list(supported_locales)
        self._sources: list[tuple[str, Path]] = []
        self._messages: dict[str, dict[str, str]] = {}

    def add_source(self, namespace: str, locale_dir: Path) -> None:
        """Queue a module's locale directory for loading under a namespace."""
        self._sources.append((namespace, Path(locale_dir)))

    def load(self) -> None:
        """Read and flatten all registered JSON files.

        Missing <locale>.json files for declared supported_locales log a
        warning but do not raise. Malformed JSON raises ValueError.
        """
        self._messages = {locale: {} for locale in self.supported_locales}

        for namespace, locale_dir in self._sources:
            for locale in self.supported_locales:
                path = locale_dir / f"{locale}.json"
                if not path.is_file():
                    logger.warning(
                        "Missing locale file for namespace '%s': %s",
                        namespace,
                        path,
                    )
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON in {path}: {exc}") from exc
                if not isinstance(raw, dict):
                    raise ValueError(f"{path} must contain a JSON object at the top level")
                flat = flatten_messages(raw, prefix=namespace)
                self._messages[locale].update(flat)

    def available_locales(self) -> list[str]:
        """Locales that have at least one loaded message."""
        return [locale for locale, msgs in self._messages.items() if msgs]

    def messages(self, locale: str) -> dict[str, str]:
        """Flat dotted-key map for the given locale. Empty dict if unknown."""
        return dict(self._messages.get(locale, {}))
```

- [ ] **Step 9: Verify all tests pass**

```bash
cd framework/core && uv run pytest tests/test_i18n.py -v
```

Expected: 11 passed.

- [ ] **Step 10: Commit**

```bash
git add framework/core/simple_module_core/i18n.py \
        framework/core/tests/test_i18n.py \
        framework/core/pyproject.toml
git commit -m "feat(core): add I18nRegistry for per-module locale JSON loading"
```

---

## Task 2: `Translator` — interpolation

**Files:**
- Modify: `framework/core/simple_module_core/i18n.py`
- Modify: `framework/core/tests/test_i18n.py`

**Context:** Simple string interpolation with `{name}` placeholders via `str.format_map` with a default-dict that returns the placeholder if the param is missing. No plurals yet — that comes in Task 3.

- [ ] **Step 1: Write failing tests for interpolation + fallback**

Append to `framework/core/tests/test_i18n.py`:

```python
from simple_module_core.i18n import Translator


class TestTranslator:
    def _registry_with(self, locale_data: dict[str, dict[str, str]]) -> I18nRegistry:
        """Build a registry directly from in-memory data (bypasses filesystem)."""
        reg = I18nRegistry(default_locale="en", supported_locales=list(locale_data.keys()))
        reg._messages = locale_data  # noqa: SLF001 — test-only shortcut
        return reg

    def test_returns_string_for_known_key(self) -> None:
        reg = self._registry_with({"en": {"hello": "Hello"}})
        t = Translator(reg, locale="en", default_locale="en")
        assert t.t("hello") == "Hello"

    def test_interpolates_named_placeholders(self) -> None:
        reg = self._registry_with({"en": {"greeting": "Hello, {name}"}})
        t = Translator(reg, locale="en", default_locale="en")
        assert t.t("greeting", name="Ana") == "Hello, Ana"

    def test_missing_placeholder_keeps_brace_form(self) -> None:
        reg = self._registry_with({"en": {"greeting": "Hello, {name}"}})
        t = Translator(reg, locale="en", default_locale="en")
        # Param not supplied — value is the raw placeholder, not an exception.
        assert t.t("greeting") == "Hello, {name}"

    def test_falls_back_to_default_locale(self) -> None:
        reg = self._registry_with({"en": {"hello": "Hello"}, "es": {}})
        t = Translator(reg, locale="es", default_locale="en")
        assert t.t("hello") == "Hello"

    def test_unknown_key_returns_key(self) -> None:
        reg = self._registry_with({"en": {}})
        t = Translator(reg, locale="en", default_locale="en")
        assert t.t("missing.key") == "missing.key"

    def test_prefers_requested_locale_over_default(self) -> None:
        reg = self._registry_with({"en": {"hello": "Hello"}, "es": {"hello": "Hola"}})
        t = Translator(reg, locale="es", default_locale="en")
        assert t.t("hello") == "Hola"
```

- [ ] **Step 2: Run and verify failure**

```bash
cd framework/core && uv run pytest tests/test_i18n.py::TestTranslator -v
```

Expected: `ImportError: cannot import name 'Translator'`.

- [ ] **Step 3: Implement `Translator` (interpolation only, no plurals yet)**

Append to `framework/core/simple_module_core/i18n.py`:

```python
class _SafeFormatDict(dict):
    """Dict that returns ``{key}`` for missing keys so str.format_map doesn't raise."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class Translator:
    """Request-scoped translator bound to a specific locale.

    Construct via::

        Translator(registry, locale=request.state.locale, default_locale="en")

    Resolution order for :meth:`t`:

    1. Look up key in ``locale``; if missing, fall back to ``default_locale``.
    2. If still missing, return the key itself (with a debug log).
    3. Interpolate ``{name}``-style placeholders using supplied kwargs.
       Missing placeholders are left as ``{name}`` (not raised).
    """

    def __init__(
        self,
        registry: I18nRegistry,
        locale: str,
        default_locale: str,
    ) -> None:
        self._registry = registry
        self.locale = locale
        self.default_locale = default_locale

    def t(self, key: str, **params: Any) -> str:
        """Translate ``key`` with optional interpolation."""
        template = self._lookup(key)
        if template is None:
            logger.debug("i18n: missing key '%s' in locale '%s'", key, self.locale)
            return key
        return template.format_map(_SafeFormatDict(params))

    def _lookup(self, key: str) -> str | None:
        msgs = self._registry.messages(self.locale)
        if key in msgs:
            return msgs[key]
        if self.locale != self.default_locale:
            default = self._registry.messages(self.default_locale)
            if key in default:
                return default[key]
        return None
```

- [ ] **Step 4: Run and verify all tests pass**

```bash
cd framework/core && uv run pytest tests/test_i18n.py -v
```

Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add framework/core/simple_module_core/i18n.py framework/core/tests/test_i18n.py
git commit -m "feat(core): add Translator with {name} interpolation and locale fallback"
```

---

## Task 3: Plural resolution via Babel

**Files:**
- Modify: `framework/core/simple_module_core/i18n.py`
- Modify: `framework/core/tests/test_i18n.py`

**Context:** When `count` is in params and the key has `_<form>` variants, resolve the CLDR plural category via `babel.Locale(locale).plural_form` and pick the matching suffixed key. Falls back to the un-suffixed key if no variant exists.

- [ ] **Step 1: Write failing plural tests**

Append to `framework/core/tests/test_i18n.py`:

```python
class TestTranslatorPlurals:
    def test_english_one(self) -> None:
        reg = Translator.__new__(Translator)  # bypass init for brevity
        # Proper setup via factory:
        registry = I18nRegistry(default_locale="en", supported_locales=["en"])
        registry._messages = {  # noqa: SLF001
            "en": {
                "items_one": "{count} item",
                "items_other": "{count} items",
            }
        }
        t = Translator(registry, locale="en", default_locale="en")
        assert t.t("items", count=1) == "1 item"

    def test_english_other(self) -> None:
        registry = I18nRegistry(default_locale="en", supported_locales=["en"])
        registry._messages = {  # noqa: SLF001
            "en": {"items_one": "{count} item", "items_other": "{count} items"}
        }
        t = Translator(registry, locale="en", default_locale="en")
        assert t.t("items", count=5) == "5 items"

    def test_russian_few_many(self) -> None:
        registry = I18nRegistry(default_locale="en", supported_locales=["en", "ru"])
        registry._messages = {  # noqa: SLF001
            "ru": {
                "items_one": "{count} предмет",
                "items_few": "{count} предмета",
                "items_many": "{count} предметов",
                "items_other": "{count} предмета",
            }
        }
        t = Translator(registry, locale="ru", default_locale="en")
        # Russian: 1 -> one, 2 -> few, 5 -> many
        assert t.t("items", count=1) == "1 предмет"
        assert t.t("items", count=2) == "2 предмета"
        assert t.t("items", count=5) == "5 предметов"

    def test_no_count_no_plural_resolution(self) -> None:
        registry = I18nRegistry(default_locale="en", supported_locales=["en"])
        registry._messages = {"en": {"items": "Items"}}  # noqa: SLF001
        t = Translator(registry, locale="en", default_locale="en")
        # No 'count' param -> plain lookup.
        assert t.t("items") == "Items"

    def test_falls_back_to_other_if_form_missing(self) -> None:
        registry = I18nRegistry(default_locale="en", supported_locales=["en"])
        # Only _other defined; 1 should still resolve via _other.
        registry._messages = {"en": {"items_other": "{count} items"}}  # noqa: SLF001
        t = Translator(registry, locale="en", default_locale="en")
        assert t.t("items", count=1) == "1 items"

    def test_unknown_plural_key_returns_key(self) -> None:
        registry = I18nRegistry(default_locale="en", supported_locales=["en"])
        registry._messages = {"en": {}}  # noqa: SLF001
        t = Translator(registry, locale="en", default_locale="en")
        assert t.t("missing", count=1) == "missing"
```

- [ ] **Step 2: Run and verify failure**

```bash
cd framework/core && uv run pytest tests/test_i18n.py::TestTranslatorPlurals -v
```

Expected: first test fails — `items_one` lookup only tries the base key.

- [ ] **Step 3: Implement plural resolution**

Replace the `Translator.t` method in `framework/core/simple_module_core/i18n.py` with:

```python
    def t(self, key: str, **params: Any) -> str:
        """Translate ``key`` with optional interpolation and plural resolution.

        When ``count`` is in params, look up ``<key>_<plural_form>`` using
        Babel's CLDR plural rule for the active locale, falling back to
        ``<key>_other`` and finally ``<key>``.
        """
        resolved_key = self._resolve_plural_key(key, params)
        template = self._lookup(resolved_key)
        if template is None and resolved_key != key:
            template = self._lookup(key)
        if template is None:
            logger.debug("i18n: missing key '%s' in locale '%s'", key, self.locale)
            return key
        return template.format_map(_SafeFormatDict(params))

    def _resolve_plural_key(self, key: str, params: dict[str, Any]) -> str:
        count = params.get("count")
        if count is None:
            return key
        form = _plural_form(self.locale, count)
        # Prefer the exact form; fall back to _other if that form has no entry.
        candidate = f"{key}_{form}"
        if self._lookup(candidate) is not None:
            return candidate
        other = f"{key}_other"
        if self._lookup(other) is not None:
            return other
        return key
```

Add the `_plural_form` helper above the class (after the imports):

```python
from functools import lru_cache

from babel import Locale


@lru_cache(maxsize=64)
def _plural_rule(locale: str):  # type: ignore[no-untyped-def]
    """Cached CLDR plural rule for a locale tag (e.g. 'en', 'ru', 'pt_BR')."""
    return Locale.parse(locale).plural_form


def _plural_form(locale: str, count: float) -> str:
    """Return CLDR plural category ('one', 'few', 'many', 'other', ...).

    Falls back to 'other' if the locale cannot be parsed by Babel.
    """
    try:
        rule = _plural_rule(locale)
    except Exception:  # noqa: BLE001
        return "other"
    return rule(count)
```

- [ ] **Step 4: Run and verify plural tests pass**

```bash
cd framework/core && uv run pytest tests/test_i18n.py -v
```

Expected: 23 passed.

- [ ] **Step 5: Commit**

```bash
git add framework/core/simple_module_core/i18n.py framework/core/tests/test_i18n.py
git commit -m "feat(core): resolve plural forms via Babel CLDR rules"
```

---

## Task 4: `locale_dirs()` on `ModuleBase` + exports

**Files:**
- Modify: `framework/core/simple_module_core/module.py`
- Modify: `framework/core/simple_module_core/__init__.py`
- Modify: `framework/core/tests/test_module_base.py`

**Context:** Give modules a hook to declare their locale directories. Pure metadata method (no registration arg), matches `template_dirs()`. Export `I18nRegistry` and `Translator` from the core package.

- [ ] **Step 1: Write failing test for the new method**

Append to `framework/core/tests/test_module_base.py`:

```python
def test_module_base_locale_dirs_defaults_empty() -> None:
    from simple_module_core import ModuleBase, ModuleMeta

    class _M(ModuleBase):
        meta = ModuleMeta(name="X")

    assert _M().locale_dirs() == {}


def test_module_base_locale_dirs_can_be_overridden(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from simple_module_core import ModuleBase, ModuleMeta

    class _M(ModuleBase):
        meta = ModuleMeta(name="X")

        def locale_dirs(self):  # type: ignore[no-untyped-def]
            return {"x": tmp_path}

    assert _M().locale_dirs() == {"x": tmp_path}
```

- [ ] **Step 2: Run and verify failure**

```bash
cd framework/core && uv run pytest tests/test_module_base.py -v
```

Expected: `AttributeError: '_M' object has no attribute 'locale_dirs'`.

- [ ] **Step 3: Add `locale_dirs()` method**

In `framework/core/simple_module_core/module.py`, after the `static_mounts` method (around line 145), insert:

```python
    def locale_dirs(self) -> dict[str, Path]:
        """Return ``{namespace: directory}`` mapping for locale JSON files.

        Default returns an empty dict. Override to contribute a module's
        locales::

            return {
                "products": importlib.resources.files(__package__) / "locales"
            }

        The namespace becomes the key prefix in the merged i18n registry.
        A file ``locales/en.json`` containing ``{"browse": {"title": "X"}}``
        becomes the key ``products.browse.title`` at runtime.

        Convention: use the module's lowercase name as the namespace.
        """
        return {}
```

- [ ] **Step 4: Export `I18nRegistry` and `Translator` from core**

In `framework/core/simple_module_core/__init__.py`, add the import and extend `__all__`:

```python
from simple_module_core.i18n import I18nRegistry, Translator
```

And in the `__all__` list (alphabetically):

```python
    "I18nRegistry",
```
(after `"HealthStatus"`)

```python
    "Translator",
```
(after `"PermissionRegistry"`)

- [ ] **Step 5: Run tests**

```bash
cd framework/core && uv run pytest -v
```

Expected: all tests pass (existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add framework/core/simple_module_core/module.py \
        framework/core/simple_module_core/__init__.py \
        framework/core/tests/test_module_base.py
git commit -m "feat(core): add ModuleBase.locale_dirs() and export i18n types"
```

---

## Task 5: i18n settings + `LocaleMiddleware`

**Files:**
- Modify: `framework/hosting/simple_module_hosting/settings.py`
- Create: `framework/hosting/simple_module_hosting/i18n_middleware.py`
- Create: `framework/hosting/tests/test_locale_middleware.py`

**Context:** `LocaleMiddleware` resolves the active locale per request from cookie → Accept-Language → default, and sets `request.state.locale`. Runs as an ASGI-style middleware like the existing `TenantMiddleware`.

- [ ] **Step 1: Add i18n settings fields**

Edit `framework/hosting/simple_module_hosting/settings.py`. After the `tenant_header` field (line 49), add:

```python
    # Internationalization
    i18n_default_locale: str = "en"
    """Locale used when no cookie, Accept-Language, or supported locale match."""

    i18n_supported_locales: list[str] = ["en"]
    """Locales the host will serve. Must include i18n_default_locale.

    Set via env as JSON-style list, e.g. ``SM_I18N_SUPPORTED_LOCALES='["en","es"]'``.
    """

    i18n_cookie_name: str = "locale"
    """Name of the cookie that overrides browser Accept-Language."""
```

- [ ] **Step 2: Write failing middleware tests**

Create `framework/hosting/tests/test_locale_middleware.py`:

```python
"""Tests for LocaleMiddleware request-state population."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from simple_module_hosting.i18n_middleware import LocaleMiddleware


def _build_app(supported: list[str], default: str, cookie_name: str = "locale") -> Starlette:
    async def endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"locale": request.state.locale})

    app = Starlette(routes=[Route("/", endpoint)])
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=supported,
        default_locale=default,
        cookie_name=cookie_name,
    )
    return app


def test_uses_cookie_when_present_and_supported() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", cookies={"locale": "es"})
    assert resp.json() == {"locale": "es"}


def test_ignores_cookie_when_locale_not_supported() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", cookies={"locale": "de"})
    # Falls through to Accept-Language, then to default (en).
    assert resp.json() == {"locale": "en"}


def test_uses_accept_language_when_no_cookie() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", headers={"Accept-Language": "es,en;q=0.8"})
    assert resp.json() == {"locale": "es"}


def test_prefix_match_accept_language() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    # "es-MX" should match supported "es" via prefix.
    resp = client.get("/", headers={"Accept-Language": "es-MX"})
    assert resp.json() == {"locale": "es"}


def test_falls_back_to_default_when_nothing_matches() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get("/", headers={"Accept-Language": "de,fr;q=0.5"})
    assert resp.json() == {"locale": "en"}


def test_cookie_takes_precedence_over_accept_language() -> None:
    app = _build_app(["en", "es"], "en")
    client = TestClient(app)
    resp = client.get(
        "/",
        cookies={"locale": "es"},
        headers={"Accept-Language": "de"},
    )
    assert resp.json() == {"locale": "es"}


def test_custom_cookie_name() -> None:
    app = _build_app(["en", "es"], "en", cookie_name="lang")
    client = TestClient(app)
    resp = client.get("/", cookies={"lang": "es"})
    assert resp.json() == {"locale": "es"}
```

- [ ] **Step 3: Run and verify failure**

```bash
cd framework/hosting && uv run pytest tests/test_locale_middleware.py -v
```

Expected: `ModuleNotFoundError: No module named 'simple_module_hosting.i18n_middleware'`.

- [ ] **Step 4: Implement `LocaleMiddleware`**

Create `framework/hosting/simple_module_hosting/i18n_middleware.py`:

```python
"""LocaleMiddleware — resolve active locale from cookie / Accept-Language / default."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class LocaleMiddleware:
    """Set ``request.state.locale`` based on cookie, Accept-Language, and default.

    Resolution order:

    1. Cookie named ``cookie_name``, validated against ``supported_locales``.
    2. ``Accept-Language`` header, negotiated against supported_locales via
       longest-prefix match (``es-MX`` matches supported ``es``).
    3. ``default_locale``.

    Runs as a pure ASGI middleware (no BaseHTTPMiddleware) to match the rest
    of the framework's middleware stack.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        supported_locales: list[str],
        default_locale: str,
        cookie_name: str = "locale",
    ) -> None:
        self.app = app
        self.supported = list(supported_locales)
        self.default_locale = default_locale
        self.cookie_name = cookie_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        locale = self._resolve(request)
        request.state.locale = locale
        await self.app(scope, receive, send)

    def _resolve(self, request: Request) -> str:
        # 1. Cookie.
        cookie = request.cookies.get(self.cookie_name)
        if cookie and cookie in self.supported:
            return cookie

        # 2. Accept-Language.
        accept = Headers(scope=request.scope).get("accept-language")
        if accept:
            matched = self._negotiate(accept)
            if matched:
                return matched

        # 3. Default.
        return self.default_locale

    def _negotiate(self, accept_language: str) -> str | None:
        """Parse Accept-Language and return the highest-q supported locale.

        Matches either exact tag or primary prefix (``es-MX`` -> ``es``).
        """
        candidates: list[tuple[float, str]] = []
        for part in accept_language.split(","):
            part = part.strip()
            if not part:
                continue
            tag, _, q_part = part.partition(";")
            tag = tag.strip().lower()
            try:
                q = float(q_part.split("=", 1)[1]) if q_part.startswith("q=") else 1.0
            except ValueError:
                q = 1.0
            candidates.append((q, tag))

        # Sort by q descending, stable.
        candidates.sort(key=lambda pair: -pair[0])

        supported_lower = {loc.lower(): loc for loc in self.supported}
        for _, tag in candidates:
            if tag in supported_lower:
                return supported_lower[tag]
            primary = tag.split("-", 1)[0]
            if primary in supported_lower:
                return supported_lower[primary]
        return None
```

- [ ] **Step 5: Run and verify all tests pass**

```bash
cd framework/hosting && uv run pytest tests/test_locale_middleware.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/simple_module_hosting/settings.py \
        framework/hosting/simple_module_hosting/i18n_middleware.py \
        framework/hosting/tests/test_locale_middleware.py
git commit -m "feat(hosting): add LocaleMiddleware with cookie + Accept-Language fallback"
```

---

## Task 6: `TranslatorDep` + registry wiring in `app_builder`

**Files:**
- Create: `framework/hosting/simple_module_hosting/i18n_deps.py`
- Create: `framework/hosting/tests/test_translator_dep.py`
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`

**Context:** Wire the `I18nRegistry` into `app.state`, install `LocaleMiddleware`, and expose a `TranslatorDep` FastAPI dependency. The registry is built in Phase 3 (app creation) from each module's `locale_dirs()` so endpoints registered in later phases can use `TranslatorDep`.

- [ ] **Step 1: Write failing dep-injection test**

Create `framework/hosting/tests/test_translator_dep.py`:

```python
"""Tests for TranslatorDep end-to-end via a minimal app."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from simple_module_core.i18n import I18nRegistry, Translator
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.i18n_middleware import LocaleMiddleware


def _build_app() -> FastAPI:
    reg = I18nRegistry(default_locale="en", supported_locales=["en", "es"])
    reg._messages = {  # noqa: SLF001
        "en": {"hello": "Hello, {name}"},
        "es": {"hello": "Hola, {name}"},
    }

    app = FastAPI()
    app.state.i18n_registry = reg
    app.state.settings_default_locale = "en"

    @app.get("/hi")
    def hi(t: TranslatorDep, name: str = "friend") -> dict[str, str]:
        return {"greeting": t.t("hello", name=name), "locale": t.locale}

    app.add_middleware(
        LocaleMiddleware,
        supported_locales=["en", "es"],
        default_locale="en",
    )
    return app


def test_translator_dep_uses_request_locale() -> None:
    client = TestClient(_build_app())
    resp = client.get("/hi?name=Ana", cookies={"locale": "es"})
    assert resp.json() == {"greeting": "Hola, Ana", "locale": "es"}


def test_translator_dep_falls_back_to_default_locale() -> None:
    client = TestClient(_build_app())
    resp = client.get("/hi?name=Ana")  # no cookie, no Accept-Language
    assert resp.json() == {"greeting": "Hello, Ana", "locale": "en"}


def test_translator_dep_returned_is_translator_instance() -> None:
    app = _build_app()

    @app.get("/type")
    def type_check(t: TranslatorDep) -> dict[str, bool]:
        return {"is_translator": isinstance(t, Translator)}

    client = TestClient(app)
    assert client.get("/type").json() == {"is_translator": True}
```

- [ ] **Step 2: Run and verify failure**

```bash
cd framework/hosting && uv run pytest tests/test_translator_dep.py -v
```

Expected: `ModuleNotFoundError: No module named 'simple_module_hosting.i18n_deps'`.

- [ ] **Step 3: Implement `TranslatorDep`**

Create `framework/hosting/simple_module_hosting/i18n_deps.py`:

```python
"""FastAPI dependency for request-scoped Translator resolution."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from simple_module_core.i18n import Translator


async def get_translator(request: Request) -> Translator:
    """Resolve a Translator bound to ``request.state.locale``.

    Reads the registry from ``request.app.state.i18n_registry`` and the
    default locale from ``request.app.state.settings_default_locale``
    (populated by create_app).

    ``request.state.locale`` is populated by LocaleMiddleware.
    """
    registry = request.app.state.i18n_registry
    default_locale = request.app.state.settings_default_locale
    locale = getattr(request.state, "locale", default_locale)
    return Translator(registry, locale=locale, default_locale=default_locale)


TranslatorDep = Annotated[Translator, Depends(get_translator)]
```

- [ ] **Step 4: Run test to confirm dep works in isolation**

```bash
cd framework/hosting && uv run pytest tests/test_translator_dep.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Wire i18n into `app_builder`**

In `framework/hosting/simple_module_hosting/app_builder.py`:

First add the import at the top, near the other `simple_module_core` imports (around line 26-29):

```python
from simple_module_core.i18n import I18nRegistry
```

Then add to the middleware import (around line 43-49):

```python
from simple_module_hosting.i18n_middleware import LocaleMiddleware
```

After line 146 (`health_registry = HealthRegistry()`), add i18n registry construction:

```python
    i18n_registry = I18nRegistry(
        default_locale=settings.i18n_default_locale,
        supported_locales=settings.i18n_supported_locales,
    )
    for mod in modules:
        for namespace, locale_dir in mod.locale_dirs().items():
            i18n_registry.add_source(namespace, locale_dir)
    # Host-level locales live at <project_root>/host/locales/.
    host_locales = _PROJECT_ROOT / "host" / "locales"
    if host_locales.is_dir():
        i18n_registry.add_source("host", host_locales)
    # Shared UI package locales.
    ui_locales = _PROJECT_ROOT / "packages" / "ui" / "locales"
    if ui_locales.is_dir():
        i18n_registry.add_source("ui", ui_locales)
    i18n_registry.load()
```

After line 172 (`app.state.settings = settings`), add:

```python
    app.state.i18n_registry = i18n_registry
    app.state.settings_default_locale = settings.i18n_default_locale
```

In the middleware block (around line 218-234), add `LocaleMiddleware` immediately before `InertiaLayoutDataMiddleware`. Since middleware is added in reverse execution order, `LocaleMiddleware` must be added **after** `InertiaLayoutDataMiddleware` to run before it. Replace the existing `add_middleware(InertiaLayoutDataMiddleware, ...)` call with this pair:

```python
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=menu_registry,
        permission_registry=perm_registry,
    )
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=settings.i18n_supported_locales,
        default_locale=settings.i18n_default_locale,
        cookie_name=settings.i18n_cookie_name,
    )
```

- [ ] **Step 6: Extend `InertiaLayoutDataMiddleware` to include locale in shared props**

In `framework/hosting/simple_module_hosting/middleware.py`, edit the `shared` dict in `InertiaLayoutDataMiddleware.__call__` (around line 232). The registry is on `request.app.state.i18n_registry`. Replace the `shared: dict = {` block with:

```python
        registry = getattr(request.app.state, "i18n_registry", None)
        locale = getattr(request.state, "locale", None)
        if registry is not None and locale is not None:
            i18n_block = {
                "locale": locale,
                "supportedLocales": registry.supported_locales,
                "messages": registry.messages(locale),
            }
        else:
            i18n_block = {
                "locale": "en",
                "supportedLocales": ["en"],
                "messages": {},
            }

        shared: dict = {
            "auth": {
                "user": (
                    {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "roles": user.roles,
                    }
                    if user
                    else None
                ),
                "isAuthenticated": is_authenticated,
                "permissions": frontend_permissions,
            },
            "menus": self.menu_registry.get_for_user(
                is_authenticated=is_authenticated,
                roles=roles,
            ),
            "csrf_token": secrets.token_urlsafe(32) if is_authenticated else "",
            "i18n": i18n_block,
        }
```

- [ ] **Step 7: Run full hosting test suite**

```bash
cd framework/hosting && uv run pytest -v
```

Expected: all tests pass (including the existing `test_app.py`). If `test_app.py` fails with `AttributeError` on `i18n_registry`, it means an assertion there needs updating — add a minimal check that the registry exists but do not break existing coverage.

- [ ] **Step 8: Commit**

```bash
git add framework/hosting/simple_module_hosting/i18n_deps.py \
        framework/hosting/simple_module_hosting/app_builder.py \
        framework/hosting/simple_module_hosting/middleware.py \
        framework/hosting/tests/test_translator_dep.py
git commit -m "feat(hosting): wire I18nRegistry, LocaleMiddleware, TranslatorDep"
```

---

## Task 7: Emit `generated-resources.ts` for frontend typing

**Files:**
- Create: `framework/hosting/simple_module_hosting/i18n_manifest.py`
- Create: `framework/hosting/tests/test_i18n_manifest.py`
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`

**Context:** Emit a `generated-resources.ts` file alongside `modules.generated.ts` whose only job is to give i18next a typed shape to augment against. Values are empty strings; only the keys matter.

- [ ] **Step 1: Write failing test**

Create `framework/hosting/tests/test_i18n_manifest.py`:

```python
"""Tests for generated-resources.ts emission."""

from __future__ import annotations

from pathlib import Path

from simple_module_core.i18n import I18nRegistry
from simple_module_hosting.i18n_manifest import write_generated_resources


def test_writes_file_with_flat_keys(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {  # noqa: SLF001
        "en": {
            "host.landing.title": "Hello",
            "products.browse.title": "Products",
        }
    }
    out = write_generated_resources(reg, tmp_path)
    text = out.read_text()
    assert "'host.landing.title': ''" in text
    assert "'products.browse.title': ''" in text
    assert "AUTO-GENERATED" in text
    assert "export default" in text


def test_keys_are_sorted(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"z.a": "", "a.z": "", "m.m": ""}}  # noqa: SLF001
    out = write_generated_resources(reg, tmp_path)
    text = out.read_text()
    a_idx = text.index("'a.z'")
    m_idx = text.index("'m.m'")
    z_idx = text.index("'z.a'")
    assert a_idx < m_idx < z_idx


def test_only_writes_when_changed(tmp_path: Path) -> None:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"k": "v"}}  # noqa: SLF001
    out = write_generated_resources(reg, tmp_path)
    first_mtime = out.stat().st_mtime_ns
    # Second call with identical content should not re-touch the file.
    write_generated_resources(reg, tmp_path)
    assert out.stat().st_mtime_ns == first_mtime
```

- [ ] **Step 2: Run and verify failure**

```bash
cd framework/hosting && uv run pytest tests/test_i18n_manifest.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the manifest writer**

Create `framework/hosting/simple_module_hosting/i18n_manifest.py`:

```python
"""Emit generated-resources.ts for frontend TypeScript type augmentation."""

from __future__ import annotations

import logging
from pathlib import Path

from simple_module_core.i18n import I18nRegistry

logger = logging.getLogger(__name__)

_HEADER = """\
// AUTO-GENERATED by simple_module_hosting.i18n_manifest — do not edit by hand.
// Regenerate by booting the host in development mode.
//
// Shape of the default locale's keys. Values are empty strings; only the
// key set is consumed by TypeScript via i18n-types.ts module augmentation.
"""


def write_generated_resources(registry: I18nRegistry, output_dir: Path) -> Path:
    """Write ``generated-resources.ts`` into ``output_dir``.

    Emits the default-locale key shape with empty string values, so i18next's
    ``CustomTypeOptions['resources']`` augmentation infers the available keys.
    Writes only when content differs from what's on disk.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "generated-resources.ts"

    default_locale = registry.default_locale
    messages = registry.messages(default_locale)
    keys = sorted(messages.keys())

    lines = [_HEADER, "", "export default {", "  translation: {"]
    for key in keys:
        # Single-quote key, empty-string value, trailing comma for diff-friendliness.
        lines.append(f"    '{key}': '',")
    lines.append("  },")
    lines.append("} as const;")
    lines.append("")
    payload = "\n".join(lines)

    try:
        existing = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = None

    if existing != payload:
        target.write_text(payload, encoding="utf-8")
        logger.info("Wrote %s (%d keys)", target.name, len(keys))

    return target
```

- [ ] **Step 4: Run tests**

```bash
cd framework/hosting && uv run pytest tests/test_i18n_manifest.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Wire emission into `app_builder`**

In `framework/hosting/simple_module_hosting/app_builder.py`, find the block that emits `modules.generated.ts` (the `write_module_pages_manifest` call around lines 130-139). Immediately after it, add generation of resources:

```python
        try:
            from simple_module_hosting.i18n_manifest import write_generated_resources

            if client_app.is_dir():
                write_generated_resources(i18n_registry, client_app)
        except Exception:
            logger.exception(
                "Failed to write generated-resources.ts — frontend types will be stale"
            )
```

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/simple_module_hosting/i18n_manifest.py \
        framework/hosting/simple_module_hosting/app_builder.py \
        framework/hosting/tests/test_i18n_manifest.py
git commit -m "feat(hosting): emit generated-resources.ts for frontend i18next typing"
```

---

## Task 8: `packages/i18n` workspace package

**Files:**
- Create: `packages/i18n/package.json`
- Create: `packages/i18n/tsconfig.json`
- Create: `packages/i18n/src/index.ts`
- Modify: `host/client_app/package.json`
- Modify: `packages/ui/package.json`

**Context:** A thin wrapper around `i18next` + `react-i18next` exposing only the four symbols the rest of the app needs: `configureI18n`, `updateI18n`, `useT`, `t`.

- [ ] **Step 1: Create `package.json` for the workspace**

Create `packages/i18n/package.json`:

```json
{
  "name": "@simple-module/i18n",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "dependencies": {
    "i18next": "^23.15.0",
    "react": "^19.0.0",
    "react-i18next": "^15.1.0"
  },
  "devDependencies": {
    "@simple-module/tsconfig": "*"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json`**

Create `packages/i18n/tsconfig.json`:

```json
{
  "extends": "@simple-module/tsconfig/base.json",
  "include": ["src"]
}
```

Check `packages/tsconfig/base.json` exists and has reasonable React TS settings. If it doesn't already include `"jsx": "react-jsx"`, add it.

- [ ] **Step 3: Write `src/index.ts`**

Create `packages/i18n/src/index.ts`:

```ts
/**
 * Localization primitives — thin wrapper over i18next + react-i18next.
 *
 * Exports the surface the rest of the host consumes:
 *  - configureI18n: call once at boot with the active-locale messages
 *  - updateI18n: call when an Inertia visit brings a new locale
 *  - useT: React hook for translation
 *  - t: non-hook accessor (for use in schemas or utilities)
 */

import i18next from 'i18next';
import { initReactI18next, useTranslation } from 'react-i18next';

type Messages = Record<string, string>;

interface ConfigureOptions {
  locale: string;
  messages: Messages;
}

let configured = false;

export function configureI18n(opts: ConfigureOptions): void {
  if (configured) {
    updateI18n(opts);
    return;
  }
  i18next.use(initReactI18next).init({
    lng: opts.locale,
    fallbackLng: opts.locale,
    resources: {
      [opts.locale]: { translation: opts.messages },
    },
    interpolation: {
      escapeValue: false, // React already escapes
      prefix: '{',
      suffix: '}',
    },
    returnNull: false,
  });
  configured = true;
}

export function updateI18n(opts: ConfigureOptions): void {
  i18next.addResourceBundle(
    opts.locale,
    'translation',
    opts.messages,
    /* deep */ true,
    /* overwrite */ true,
  );
  if (i18next.language !== opts.locale) {
    i18next.changeLanguage(opts.locale);
  }
}

export { useTranslation as useT } from 'react-i18next';
export { t } from 'i18next';
```

- [ ] **Step 4: Add dependencies to `host/client_app/package.json`**

Edit `host/client_app/package.json`. In `dependencies`, add:

```json
    "@simple-module/i18n": "*",
    "i18next": "^23.15.0",
    "react-i18next": "^15.1.0",
```

(place alphabetically; `@simple-module/i18n` near `@inertiajs/react`)

- [ ] **Step 5: Add the dep to `packages/ui/package.json`**

Edit `packages/ui/package.json`. In `dependencies`, add:

```json
    "@simple-module/i18n": "*",
```

- [ ] **Step 6: Install JS deps**

```bash
npm install
```

Expected: packages resolve; new workspace member `@simple-module/i18n` shows as linked.

- [ ] **Step 7: Verify TypeScript compiles**

```bash
npx tsc --noEmit -p host/client_app/tsconfig.json
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add packages/i18n host/client_app/package.json packages/ui/package.json package-lock.json
git commit -m "feat(i18n): add @simple-module/i18n workspace package"
```

---

## Task 9: `host/client_app/i18n.ts` + `i18n-types.ts` + stub `generated-resources.ts`

**Files:**
- Create: `host/client_app/i18n.ts`
- Create: `host/client_app/i18n-types.ts`
- Create: `host/client_app/generated-resources.ts` (stub — real one emitted at boot)
- Modify: `host/client_app/main.tsx`
- Modify: `host/client_app/app.tsx`

**Context:** Wire i18next into the Inertia root. `i18n-types.ts` activates the TS augmentation; `i18n.ts` handles the boot call and locale-change detection on navigation.

- [ ] **Step 1: Create the stub `generated-resources.ts`**

Create `host/client_app/generated-resources.ts`:

```ts
// AUTO-GENERATED by simple_module_hosting.i18n_manifest — do not edit by hand.
// This file is replaced each time the host boots in development mode. The
// stub committed to git holds only the keys we need for type-checking when
// CI runs before the backend boots.

export default {
  translation: {} as Record<string, string>,
} as const;
```

- [ ] **Step 2: Create `i18n-types.ts`**

Create `host/client_app/i18n-types.ts`:

```ts
/**
 * Activate i18next TypeScript module augmentation.
 *
 * Imported once from main.tsx so t('foo.bar') is type-checked against
 * generated-resources.ts. Runtime effect: none.
 */

import 'i18next';
import type resources from './generated-resources';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: typeof resources;
  }
}
```

- [ ] **Step 3: Create `i18n.ts`**

Create `host/client_app/i18n.ts`:

```ts
/**
 * Initial wiring for @simple-module/i18n inside the Inertia app.
 *
 * Reads {locale, messages} from Inertia shared props and calls
 * configureI18n on boot; on every successful navigation, checks whether
 * the active locale changed and updates the i18next resources.
 */

import { router, type PageProps } from '@inertiajs/react';
import { configureI18n, updateI18n } from '@simple-module/i18n';

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  messages: Record<string, string>;
}

export function bootI18nFromInitialPage(props: PageProps): void {
  const i18n = (props as unknown as { i18n?: I18nSharedProps }).i18n;
  if (!i18n) {
    configureI18n({ locale: 'en', messages: {} });
    return;
  }
  configureI18n({ locale: i18n.locale, messages: i18n.messages });
}

let activeLocale: string | null = null;

export function subscribeI18nToNavigation(): () => void {
  return router.on('success', (event) => {
    const i18n = (event.detail.page.props as unknown as { i18n?: I18nSharedProps }).i18n;
    if (!i18n) return;
    if (i18n.locale !== activeLocale) {
      updateI18n({ locale: i18n.locale, messages: i18n.messages });
      activeLocale = i18n.locale;
    }
  });
}
```

- [ ] **Step 4: Import types in `main.tsx`**

Edit `host/client_app/main.tsx`:

```ts
import './styles.css';
import './i18n-types';
import './app';
```

- [ ] **Step 5: Wire `configureI18n` + subscription in `app.tsx`**

Edit `host/client_app/app.tsx`. Replace the existing file content with:

```tsx
import { createInertiaApp, router } from '@inertiajs/react';
import { ErrorBoundary } from '@simple-module/ui/components/ErrorBoundary';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';
import { resolvePage } from './pages';

createInertiaApp({
  resolve: async (name) => {
    const page = await resolvePage(name);
    return page;
  },
  setup({ el, App, props }) {
    bootI18nFromInitialPage(props.initialPage.props);

    function Root() {
      const boundaryRef = useRef<ErrorBoundary>(null);

      useEffect(() => {
        const stopReset = router.on('navigate', () => boundaryRef.current?.reset());
        const stopI18n = subscribeI18nToNavigation();
        return () => {
          stopReset();
          stopI18n();
        };
      }, []);

      return (
        <ErrorBoundary ref={boundaryRef}>
          <App {...props} />
        </ErrorBoundary>
      );
    }

    createRoot(el).render(<Root />);
  },
  progress: {
    color: '#4B5563',
    delay: 150,
  },
});
```

- [ ] **Step 6: Run typecheck**

```bash
npx tsc --noEmit -p host/client_app/tsconfig.json
```

Expected: no errors. The empty `generated-resources.ts` stub means any `t()` key currently compiles (no keys to check against); narrowing comes once the backend boots and overwrites the stub.

- [ ] **Step 7: Commit**

```bash
git add host/client_app/i18n.ts host/client_app/i18n-types.ts \
        host/client_app/generated-resources.ts host/client_app/main.tsx \
        host/client_app/app.tsx
git commit -m "feat(client): wire @simple-module/i18n into Inertia boot"
```

---

## Task 10: `.gitignore` generated files

**Files:**
- Modify: `.gitignore` (root)

**Context:** `generated-resources.ts` is written every time the host boots in dev, like `modules.generated.ts` and friends. Keep the stub in git so fresh checkouts compile, but ignore the in-place edits.

- [ ] **Step 1: Check existing ignored generated files**

```bash
grep -n "modules.generated" .gitignore
```

Expected: entries for the existing generated files. If the generated files are NOT ignored (they may be committed on purpose so CI sees them), skip this task entirely and commit nothing.

- [ ] **Step 2: If they are ignored, add our generated file**

Append to `.gitignore`:

```
# Generated by simple_module_hosting.i18n_manifest at boot; stub is checked in
host/client_app/generated-resources.ts
```

**Stop and ask:** if `modules.generated.ts` is already committed (grep above returned no match), do NOT add this line — commit the generated file too for consistency. If `modules.generated.ts` is in `.gitignore`, add the line above.

- [ ] **Step 3: Commit (if modified)**

```bash
git add .gitignore
git commit -m "chore: ignore generated-resources.ts like other manifest outputs"
```

---

## Task 11: Switcher endpoint

**Files:**
- Create: `host/routes_i18n.py`
- Modify: `host/main.py`
- Create: `host/tests/test_routes_i18n.py`

**Context:** `POST /i18n/set-locale` validates the locale against supported, sets a 1-year cookie, and 303-redirects to `Referer`.

- [ ] **Step 1: Find where host-level routes are registered**

```bash
grep -n "include_router" host/main.py host/routes.py
```

Note the wiring. `host/routes.py` exports `router`; `host/main.py` should include it into `app`.

- [ ] **Step 2: Write failing endpoint test**

Create `host/tests/test_routes_i18n.py`:

```python
"""Tests for the locale-switcher endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from host.routes_i18n import router as i18n_router


def _build_app(supported: list[str]) -> FastAPI:
    app = FastAPI()
    app.state.settings_supported_locales = supported
    app.state.settings_cookie_name = "locale"
    app.include_router(i18n_router)
    return app


def test_sets_cookie_on_valid_locale() -> None:
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post(
        "/i18n/set-locale",
        data={"locale": "es"},
        headers={"Referer": "/dashboard"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    cookie = resp.cookies.get("locale")
    assert cookie == "es"


def test_rejects_unsupported_locale() -> None:
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post("/i18n/set-locale", data={"locale": "de"})
    assert resp.status_code == 422


def test_redirects_to_root_when_no_referer() -> None:
    client = TestClient(_build_app(["en", "es"]), follow_redirects=False)
    resp = client.post("/i18n/set-locale", data={"locale": "es"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
```

- [ ] **Step 3: Run and verify failure**

```bash
uv run pytest host/tests/test_routes_i18n.py -v
```

Expected: `ModuleNotFoundError: No module named 'host.routes_i18n'`.

- [ ] **Step 4: Implement the router**

Create `host/routes_i18n.py`:

```python
"""Locale switcher endpoint.

POST /i18n/set-locale with form body ``locale=<code>``. Validates against
the host's supported locales, sets a 1-year cookie, and 303-redirects to
the Referer (falls back to ``/``).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import RedirectResponse

router = APIRouter()

_ONE_YEAR_SECONDS = 60 * 60 * 24 * 365


@router.post("/i18n/set-locale", response_model=None)
async def set_locale(request: Request, locale: str = Form(...)) -> RedirectResponse:
    """Persist the user's locale choice in a long-lived cookie."""
    supported: list[str] = request.app.state.settings_supported_locales
    cookie_name: str = request.app.state.settings_cookie_name

    if locale not in supported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported locale '{locale}' (supported: {', '.join(supported)})",
        )

    destination = request.headers.get("referer") or "/"
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(
        key=cookie_name,
        value=locale,
        max_age=_ONE_YEAR_SECONDS,
        path="/",
        samesite="lax",
        httponly=False,
    )
    return response
```

- [ ] **Step 5: Wire `settings_supported_locales` / `settings_cookie_name` into `app.state`**

Edit `framework/hosting/simple_module_hosting/app_builder.py`. In the `app.state` block added in Task 6 (after `app.state.settings_default_locale = settings.i18n_default_locale`), add:

```python
    app.state.settings_supported_locales = settings.i18n_supported_locales
    app.state.settings_cookie_name = settings.i18n_cookie_name
```

- [ ] **Step 6: Include the router in the host**

Edit `host/main.py`. Find where `host.routes.router` is included and add the new router beside it. If the include is in `host/main.py`:

```python
from host.routes import router as host_router
from host.routes_i18n import router as i18n_router

# ... in startup:
app.include_router(host_router)
app.include_router(i18n_router)
```

If instead it's in `host/routes.py` via a meta-router, add the include there. (Check `host/main.py` first.)

- [ ] **Step 7: Run tests**

```bash
uv run pytest host/tests/test_routes_i18n.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add host/routes_i18n.py host/main.py host/tests/test_routes_i18n.py \
        framework/hosting/simple_module_hosting/app_builder.py
git commit -m "feat(host): add POST /i18n/set-locale switcher endpoint"
```

---

## Task 12: `<LocaleSwitcher />` component

**Files:**
- Create: `packages/ui/src/components/LocaleSwitcher.tsx`
- Modify: `packages/ui/src/layouts/AuthenticatedLayout.tsx`
- Modify: `packages/ui/src/layouts/PublicLayout.tsx`

**Context:** A shadcn `DropdownMenu` that reads `i18n.locale` / `i18n.supportedLocales` from Inertia shared props and submits a hidden form to `/i18n/set-locale` when the user picks a language. Labels for each locale are in that locale's own language (hardcoded small map).

- [ ] **Step 1: Inspect the existing DropdownMenu component**

```bash
ls packages/ui/src/components/ui | grep -i dropdown
```

Confirm `dropdown-menu.tsx` exists. If not, pick the closest-available: `select.tsx` also works.

- [ ] **Step 2: Write the switcher**

Create `packages/ui/src/components/LocaleSwitcher.tsx`:

```tsx
import { usePage } from '@inertiajs/react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@simple-module/ui/components/ui/dropdown-menu';
import { Button } from '@simple-module/ui/components/ui/button';
import { Globe } from 'lucide-react';
import { useRef } from 'react';

/**
 * Static map of locale code -> label in that locale's own language.
 * Picked before the user can read the current UI language, so labels
 * must not depend on t().
 */
const LOCALE_LABELS: Record<string, string> = {
  en: 'English',
  es: 'Español',
  de: 'Deutsch',
  fr: 'Français',
  pt: 'Português',
  ja: '日本語',
  zh: '中文',
  ru: 'Русский',
};

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  messages: Record<string, string>;
}

export function LocaleSwitcher() {
  const page = usePage<{ i18n?: I18nSharedProps }>();
  const i18n = page.props.i18n;
  const formRef = useRef<HTMLFormElement>(null);

  if (!i18n || i18n.supportedLocales.length <= 1) {
    return null;
  }

  const select = (locale: string) => {
    if (locale === i18n.locale) return;
    const form = formRef.current;
    if (!form) return;
    const input = form.elements.namedItem('locale') as HTMLInputElement;
    input.value = locale;
    form.submit();
  };

  return (
    <>
      <form
        ref={formRef}
        method="POST"
        action="/i18n/set-locale"
        style={{ display: 'none' }}
      >
        <input type="hidden" name="locale" value="" readOnly />
      </form>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Change language">
            <Globe />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {i18n.supportedLocales.map((code) => (
            <DropdownMenuItem
              key={code}
              onSelect={() => select(code)}
              data-active={code === i18n.locale}
            >
              {LOCALE_LABELS[code] ?? code}
              {code === i18n.locale && <span className="ml-auto text-xs">✓</span>}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}
```

- [ ] **Step 3: Mount it in `AuthenticatedLayout`**

Find the top-right area of `packages/ui/src/layouts/AuthenticatedLayout.tsx` (usually near the user menu). Import:

```tsx
import { LocaleSwitcher } from '@simple-module/ui/components/LocaleSwitcher';
```

Add `<LocaleSwitcher />` next to the existing user menu trigger. If there's already a user-dropdown component, add the switcher immediately before it.

- [ ] **Step 4: Mount it in `PublicLayout`**

Repeat for `packages/ui/src/layouts/PublicLayout.tsx`. Place the switcher in the top-right header area.

- [ ] **Step 5: Verify typecheck**

```bash
npx tsc --noEmit -p host/client_app/tsconfig.json
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add packages/ui/src/components/LocaleSwitcher.tsx \
        packages/ui/src/layouts/AuthenticatedLayout.tsx \
        packages/ui/src/layouts/PublicLayout.tsx
git commit -m "feat(ui): add LocaleSwitcher dropdown in layouts"
```

---

## Task 13: Vitest setup

**Files:**
- Create: `vitest.config.ts` (root)
- Create: `vitest.setup.ts` (root)
- Modify: `package.json` (root)
- Modify: `Makefile`

**Context:** Introduce Vitest as the frontend unit-test runner. Tests live next to source (`*.test.ts`, `*.test.tsx`). Fold into `make test`.

- [ ] **Step 1: Install Vitest + Testing Library**

```bash
npm install --save-dev --workspace-root \
    vitest@^2.1.0 \
    @testing-library/react@^16.1.0 \
    @testing-library/jest-dom@^6.6.0 \
    jsdom@^25.0.0
```

If `--workspace-root` isn't recognized by your npm version, run plain `npm install --save-dev ...` from the repo root (editing the root `package.json` directly is fine too — just match the key names and versions).

- [ ] **Step 2: Create `vitest.setup.ts`**

Create `vitest.setup.ts` at the repo root:

```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 3: Create `vitest.config.ts`**

Create `vitest.config.ts` at the repo root:

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react-swc';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    include: [
      'packages/**/*.test.ts',
      'packages/**/*.test.tsx',
      'host/client_app/**/*.test.ts',
      'host/client_app/**/*.test.tsx',
    ],
  },
});
```

- [ ] **Step 4: Add `test` script to root `package.json`**

Edit the root `package.json`:

```json
  "scripts": {
    "dev": "npm run --workspace host/client_app dev",
    "build": "npm run --workspace host/client_app build",
    "lint": "biome check .",
    "format": "biome format --write .",
    "typecheck": "tsc --noEmit -p host/client_app/tsconfig.json",
    "test": "vitest run"
  },
```

- [ ] **Step 5: Add `test-js` to `Makefile`**

Edit `Makefile`. Update `.PHONY` to include `test-js`:

```makefile
.PHONY: install install-py install-js dev dev-api dev-ui build test test-js lint doctor ...
```

Change the `test` target to run both:

```makefile
# Testing
test: test-py test-js

test-py:
	uv run pytest

test-js:
	npm test
```

Remove the old single-line `test:` recipe (if it stood alone with `uv run pytest`). Add `test-py` as a new target containing that command.

- [ ] **Step 6: Smoke-test Vitest on an empty suite**

```bash
npm test -- --passWithNoTests
```

Expected: vitest runs and reports 0 tests (exit 0).

If `--passWithNoTests` is not recognized, create a trivial placeholder test:

```ts
// packages/i18n/src/smoke.test.ts
import { test, expect } from 'vitest';
test('vitest is wired', () => { expect(1 + 1).toBe(2); });
```

- [ ] **Step 7: Commit**

```bash
git add vitest.config.ts vitest.setup.ts package.json Makefile package-lock.json
git commit -m "chore: add Vitest test runner for frontend"
```

---

## Task 14: Unit tests for `@simple-module/i18n`

**Files:**
- Create: `packages/i18n/src/configure.test.ts`
- (Delete `packages/i18n/src/smoke.test.ts` if you created it in Task 13.)

**Context:** Verify `configureI18n` + `t()` basic behavior + plurals.

- [ ] **Step 1: Write tests**

Create `packages/i18n/src/configure.test.ts`:

```ts
import { beforeEach, describe, expect, test } from 'vitest';
import { configureI18n, t, updateI18n } from './index';

describe('configureI18n', () => {
  beforeEach(() => {
    configureI18n({
      locale: 'en',
      messages: {
        'hello': 'Hello',
        'greeting': 'Hello, {name}',
        'items_one': '{count} item',
        'items_other': '{count} items',
      },
    });
  });

  test('returns string for known key', () => {
    expect(t('hello')).toBe('Hello');
  });

  test('interpolates named placeholders', () => {
    expect(t('greeting', { name: 'Ana' })).toBe('Hello, Ana');
  });

  test('picks _one variant for count=1', () => {
    expect(t('items', { count: 1 })).toBe('1 item');
  });

  test('picks _other variant for count>1', () => {
    expect(t('items', { count: 5 })).toBe('5 items');
  });

  test('returns the key when unknown', () => {
    expect(t('missing.key' as unknown as never)).toBe('missing.key');
  });
});

describe('updateI18n', () => {
  test('swaps the active locale', () => {
    configureI18n({ locale: 'en', messages: { hello: 'Hello' } });
    updateI18n({ locale: 'es', messages: { hello: 'Hola' } });
    expect(t('hello')).toBe('Hola');
  });
});
```

- [ ] **Step 2: Run tests**

```bash
npm test
```

Expected: 6 passed.

- [ ] **Step 3: Remove the smoke test if present**

```bash
rm -f packages/i18n/src/smoke.test.ts
```

- [ ] **Step 4: Commit**

```bash
git add packages/i18n/src/configure.test.ts
[ -f packages/i18n/src/smoke.test.ts ] && git rm packages/i18n/src/smoke.test.ts
git commit -m "test(i18n): unit tests for configureI18n, t(), updateI18n, plurals"
```

---

## Task 15: `LocaleSwitcher` component test

**Files:**
- Create: `packages/ui/src/components/LocaleSwitcher.test.tsx`

**Context:** Render-test using Inertia's `usePage` mocked. Verify that the dropdown lists all supported locales and marks the active one.

- [ ] **Step 1: Write the test**

Create `packages/ui/src/components/LocaleSwitcher.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

// Mock @inertiajs/react's usePage before importing the component under test.
vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    props: {
      i18n: {
        locale: 'en',
        supportedLocales: ['en', 'es'],
        messages: {},
      },
    },
  }),
}));

import { LocaleSwitcher } from './LocaleSwitcher';

describe('LocaleSwitcher', () => {
  test('renders when multiple locales supported', () => {
    render(<LocaleSwitcher />);
    expect(screen.getByRole('button', { name: /change language/i })).toBeInTheDocument();
  });

  test('form targets /i18n/set-locale', () => {
    const { container } = render(<LocaleSwitcher />);
    const form = container.querySelector('form');
    expect(form?.getAttribute('action')).toBe('/i18n/set-locale');
    expect(form?.getAttribute('method')?.toLowerCase()).toBe('post');
  });
});


describe('LocaleSwitcher — single locale', () => {
  beforeEach(() => {
    vi.doMock('@inertiajs/react', () => ({
      usePage: () => ({
        props: {
          i18n: { locale: 'en', supportedLocales: ['en'], messages: {} },
        },
      }),
    }));
  });

  test('does not render when only one locale supported', async () => {
    const { LocaleSwitcher: SingleSwitcher } = await import('./LocaleSwitcher');
    const { container } = render(<SingleSwitcher />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

(The single-locale test uses `vi.doMock` + dynamic import because the module mock in the top block is hoisted and reused otherwise. If this pattern fails in your Vitest version, drop the "single locale" describe block — the behavior is also covered implicitly by the `supportedLocales.length <= 1` guard.)

- [ ] **Step 2: Run tests**

```bash
npm test
```

Expected: all previous + new tests pass.

- [ ] **Step 3: Commit**

```bash
git add packages/ui/src/components/LocaleSwitcher.test.tsx
git commit -m "test(ui): LocaleSwitcher renders and targets switcher endpoint"
```

---

## Task 16: `I18nDiagnostics`

**Files:**
- Create: `framework/core/simple_module_core/diagnostics/_i18n.py`
- Modify: `framework/core/simple_module_core/diagnostics/__init__.py`
- Modify: `framework/core/simple_module_core/diagnostics/_runner.py`
- Create: `framework/core/tests/test_i18n_diagnostics.py`

**Context:** New diagnostic class that validates key parity between locale files, JSON validity, and nesting structure. Hooked into `run_diagnostics` so `make doctor` runs it automatically.

- [ ] **Step 1: Write failing tests**

Create `framework/core/tests/test_i18n_diagnostics.py`:

```python
"""Tests for I18nDiagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_core.diagnostics._i18n import I18nDiagnostics


class _FakeModule:
    def __init__(self, name: str, dirs: dict[str, Path]) -> None:
        self.meta = type("Meta", (), {"name": name})()
        self._dirs = dirs

    def locale_dirs(self) -> dict[str, Path]:
        return self._dirs


def _write(dir_: Path, lang: str, data: dict) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{lang}.json").write_text(json.dumps(data))


def test_reports_missing_locale_file(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1"})
    # no es.json
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM013" in codes


def test_reports_missing_keys_in_non_default_locale(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1", "b": "2"})
    _write(tmp_path / "p", "es", {"a": "1"})  # missing 'b'
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM014" in codes
    assert any("b" in (f.message or "") for f in findings if f.code == "SM014")


def test_reports_extra_keys_in_non_default_locale(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1"})
    _write(tmp_path / "p", "es", {"a": "1", "extra": "x"})
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM015" in codes


def test_reports_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "en.json").write_text("{ not json")
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en"], default_locale="en").run([mod])
    codes = {f.code for f in findings}
    assert "SM016" in codes


def test_no_findings_when_keys_match(tmp_path: Path) -> None:
    _write(tmp_path / "p", "en", {"a": "1"})
    _write(tmp_path / "p", "es", {"a": "1"})
    mod = _FakeModule("P", {"p": tmp_path / "p"})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    assert findings == []


def test_module_without_locales_is_silently_skipped(tmp_path: Path) -> None:
    mod = _FakeModule("P", {})
    findings = I18nDiagnostics(supported_locales=["en", "es"], default_locale="en").run([mod])
    assert findings == []
```

- [ ] **Step 2: Run and verify failure**

```bash
cd framework/core && uv run pytest tests/test_i18n_diagnostics.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `I18nDiagnostics`**

Create `framework/core/simple_module_core/diagnostics/_i18n.py`:

```python
"""Diagnostics that validate i18n locale file coverage and consistency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel
from simple_module_core.i18n import flatten_messages

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


class I18nDiagnostics:
    """Validates locale file coverage per module.

    Codes:
    - SM013: missing locale file for a supported locale.
    - SM014: non-default locale is missing keys present in the default.
    - SM015: non-default locale has keys not present in the default.
    - SM016: locale JSON fails to parse or has non-string leaves.
    """

    def __init__(self, supported_locales: list[str], default_locale: str) -> None:
        self.supported_locales = list(supported_locales)
        self.default_locale = default_locale

    def run(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        findings: list[Diagnostic] = []
        for mod in modules:
            for namespace, locale_dir in mod.locale_dirs().items():
                findings.extend(self._check_namespace(mod.meta.name, namespace, Path(locale_dir)))
        return findings

    def _check_namespace(
        self, module_name: str, namespace: str, locale_dir: Path
    ) -> list[Diagnostic]:
        findings: list[Diagnostic] = []
        per_locale_keys: dict[str, set[str]] = {}

        for locale in self.supported_locales:
            path = locale_dir / f"{locale}.json"
            if not path.is_file():
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM013",
                        message=(
                            f"Missing locale file {locale}.json for namespace '{namespace}'"
                        ),
                        module_name=module_name,
                        file=str(path),
                        suggestion=f"Create {path} (even if empty: '{{}}')",
                    )
                )
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("top-level JSON must be an object")
                flat = flatten_messages(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM016",
                        message=f"Invalid locale JSON in {path}: {exc}",
                        module_name=module_name,
                        file=str(path),
                    )
                )
                continue
            per_locale_keys[locale] = set(flat.keys())

        default_keys = per_locale_keys.get(self.default_locale, set())
        for locale, keys in per_locale_keys.items():
            if locale == self.default_locale:
                continue
            missing = default_keys - keys
            extra = keys - default_keys
            if missing:
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM014",
                        message=(
                            f"Locale '{locale}' in namespace '{namespace}' is missing keys: "
                            f"{', '.join(sorted(missing))}"
                        ),
                        module_name=module_name,
                    )
                )
            if extra:
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM015",
                        message=(
                            f"Locale '{locale}' in namespace '{namespace}' has keys not in "
                            f"default: {', '.join(sorted(extra))}"
                        ),
                        module_name=module_name,
                    )
                )
        return findings
```

- [ ] **Step 4: Export from diagnostics package**

Edit `framework/core/simple_module_core/diagnostics/__init__.py`:

```python
from simple_module_core.diagnostics._i18n import I18nDiagnostics
from simple_module_core.diagnostics._migration import MigrationDiagnostics
from simple_module_core.diagnostics._module import ModuleDiagnostics
from simple_module_core.diagnostics._runner import print_diagnostics, run_diagnostics
from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

__all__ = [
    "Diagnostic",
    "DiagnosticLevel",
    "I18nDiagnostics",
    "MigrationDiagnostics",
    "ModuleDiagnostics",
    "print_diagnostics",
    "run_diagnostics",
]
```

- [ ] **Step 5: Wire into `run_diagnostics`**

Edit `framework/core/simple_module_core/diagnostics/_runner.py`. Extend `run_diagnostics` with optional i18n params:

```python
def run_diagnostics(
    modules: list[ModuleBase],
    *,
    migration_state: dict | None = None,
    module_tables: set[str] | None = None,
    migrated_tables: set[str] | None = None,
    i18n_supported_locales: list[str] | None = None,
    i18n_default_locale: str | None = None,
) -> list[Diagnostic]:
    """Convenience function to run all diagnostics."""
    diagnostics = ModuleDiagnostics().run(modules)

    if i18n_supported_locales and i18n_default_locale:
        from simple_module_core.diagnostics._i18n import I18nDiagnostics
        diagnostics.extend(
            I18nDiagnostics(
                supported_locales=i18n_supported_locales,
                default_locale=i18n_default_locale,
            ).run(modules)
        )

    if migration_state is not None:
        # ... existing logic unchanged
        migration_diag = MigrationDiagnostics()
        diagnostics.extend(
            migration_diag.check_revision_mismatch(
                current_revision=migration_state.get("current_revision"),
                head_revision=migration_state.get("head_revision"),
            )
        )
        if module_tables is not None and migrated_tables is not None:
            diagnostics.extend(
                migration_diag.check_table_coverage(module_tables, migrated_tables)
            )

    return diagnostics
```

- [ ] **Step 6: Pass i18n settings from `app_builder`**

Edit `framework/hosting/simple_module_hosting/app_builder.py`. In the diagnostics block (around line 122-128), pass the new kwargs:

```python
        diagnostics = run_diagnostics(
            modules,
            i18n_supported_locales=settings.i18n_supported_locales,
            i18n_default_locale=settings.i18n_default_locale,
        )
```

- [ ] **Step 7: Run all tests**

```bash
cd framework/core && uv run pytest -v
```

Expected: all tests pass (new + existing).

- [ ] **Step 8: Commit**

```bash
git add framework/core/simple_module_core/diagnostics/_i18n.py \
        framework/core/simple_module_core/diagnostics/__init__.py \
        framework/core/simple_module_core/diagnostics/_runner.py \
        framework/core/tests/test_i18n_diagnostics.py \
        framework/hosting/simple_module_hosting/app_builder.py
git commit -m "feat(diagnostics): add I18nDiagnostics for locale key parity"
```

---

## Task 17: Extract strings from `packages/ui`

**Files:**
- Create: `packages/ui/locales/en.json`
- Create: `packages/ui/locales/es.json`
- Modify: `packages/ui/src/components/ErrorScreen.tsx`
- Modify: `packages/ui/src/components/PageShell.tsx` (if it has strings)
- Modify: `packages/ui/src/components/ui/empty.tsx` (leave — Empty is a primitive)

**Context:** Pull shared UI strings into `ui.*` namespace. ErrorScreen is the main source; Empty/PageShell are content-agnostic.

- [ ] **Step 1: Audit which UI components have hardcoded strings**

```bash
cd packages/ui && grep -rn -E '"[A-Z][a-z]{2,}' src/components --include='*.tsx' | grep -v 'ui/' | head -40
```

Note any user-facing strings in components you own (not the shadcn `ui/` primitives).

- [ ] **Step 2: Create `packages/ui/locales/en.json`**

Create `packages/ui/locales/en.json` with every discovered string, example:

```json
{
  "errors": {
    "generic_title": "Something went wrong",
    "generic_description": "An unexpected error occurred. Please try again.",
    "retry_button": "Try again",
    "go_home_button": "Go home"
  },
  "switcher": {
    "label": "Change language"
  }
}
```

(Adjust to what you actually find. If `ErrorScreen.tsx` uses different wording, match that verbatim so behavior is preserved.)

- [ ] **Step 3: Create the Spanish counterpart**

Create `packages/ui/locales/es.json` with the same keys:

```json
{
  "errors": {
    "generic_title": "Algo salió mal",
    "generic_description": "Ocurrió un error inesperado. Inténtalo de nuevo.",
    "retry_button": "Reintentar",
    "go_home_button": "Ir al inicio"
  },
  "switcher": {
    "label": "Cambiar idioma"
  }
}
```

- [ ] **Step 4: Swap hardcoded strings in `ErrorScreen.tsx`**

Edit `packages/ui/src/components/ErrorScreen.tsx`. At the top:

```tsx
import { useT } from '@simple-module/i18n';
```

In the component body, replace each hardcoded string with `t('ui.errors.generic_title')`, etc.

- [ ] **Step 5: Replace the aria-label in the switcher**

Edit `packages/ui/src/components/LocaleSwitcher.tsx`. Import `useT` and swap the `aria-label="Change language"` for `t('ui.switcher.label')`. (The labels for each locale stay hardcoded in `LOCALE_LABELS`.)

- [ ] **Step 6: Run typecheck**

```bash
npx tsc --noEmit -p host/client_app/tsconfig.json
```

Note: `t()` will type-check against the empty stub `generated-resources.ts` which accepts any string. Once the backend boots and emits the real one, keys will narrow. This is expected — document in the task summary.

- [ ] **Step 7: Commit**

```bash
git add packages/ui/locales packages/ui/src/components/
git commit -m "feat(ui): extract shared UI strings into packages/ui/locales"
```

---

## Task 18: Extract strings from `modules/auth`

**Files:**
- Create: `modules/auth/auth/locales/en.json`
- Create: `modules/auth/auth/locales/es.json`
- Modify: `modules/auth/auth/module.py` (add `locale_dirs()`)
- Modify: `modules/auth/auth/endpoints/*.py` (use `TranslatorDep`)

**Context:** Auth has flash messages ("Login failed", etc.) and possibly email content. Extract them.

- [ ] **Step 1: Inventory strings**

```bash
grep -rn -E '"[A-Z][a-z]{3,}' modules/auth/auth --include='*.py' | head
```

- [ ] **Step 2: Create `en.json`**

Create `modules/auth/auth/locales/en.json` with a `flash.*` / `errors.*` structure matching what you found. Example:

```json
{
  "flash": {
    "login_success": "Welcome back!",
    "logout_success": "You have been signed out."
  },
  "errors": {
    "invalid_credentials": "Invalid email or password",
    "session_expired": "Your session has expired. Please sign in again."
  }
}
```

- [ ] **Step 3: Create `es.json`**

Create `modules/auth/auth/locales/es.json` with Spanish counterparts for every key.

- [ ] **Step 4: Add `locale_dirs()` to the module class**

Edit `modules/auth/auth/module.py`. Add imports if missing:

```python
import importlib.resources
from pathlib import Path
```

Add method to the `AuthModule` class:

```python
    def locale_dirs(self) -> dict[str, Path]:
        return {"auth": Path(str(importlib.resources.files(__package__) / "locales"))}
```

- [ ] **Step 5: Swap hardcoded strings in endpoints for `TranslatorDep`**

For each endpoint in `modules/auth/auth/endpoints/` that produces a user-facing string, inject `t: TranslatorDep` and use `t.t("auth.errors.invalid_credentials")` instead of the literal. Example for a login endpoint:

```python
from simple_module_hosting.i18n_deps import TranslatorDep

@router.post("/login")
async def login(..., t: TranslatorDep) -> ...:
    if not user:
        raise HTTPException(status_code=401, detail=t.t("auth.errors.invalid_credentials"))
    flash(request, t.t("auth.flash.login_success"))
```

- [ ] **Step 6: Run auth tests**

```bash
uv run pytest modules/auth/tests -v
```

Update tests that asserted on English strings — either assert against the (locale-aware) key or assert on the English default (locale defaults to `en` in tests).

- [ ] **Step 7: Commit**

```bash
git add modules/auth
git commit -m "feat(auth): localize flash/error messages via TranslatorDep"
```

---

## Task 19: Extract strings from `modules/dashboard`

**Files:**
- Create: `modules/dashboard/dashboard/locales/en.json`
- Create: `modules/dashboard/dashboard/locales/es.json`
- Modify: `modules/dashboard/dashboard/module.py` (add `locale_dirs()`)
- Modify: `modules/dashboard/dashboard/pages/*.tsx` (use `useT()`)

**Context:** Dashboard is a thin module — mostly page titles and nav labels.

- [ ] **Step 1: Inventory strings**

```bash
grep -rn -E '"[A-Z][a-z]{3,}' modules/dashboard/dashboard --include='*.tsx' --include='*.py'
```

- [ ] **Step 2: Create `en.json` and `es.json`**

Create both files under `modules/dashboard/dashboard/locales/`. Use a structure matching the pages, e.g.:

```json
{
  "home": {
    "title": "Dashboard",
    "welcome": "Welcome back, {name}"
  }
}
```

- [ ] **Step 3: Add `locale_dirs()` to `DashboardModule`**

Same pattern as Task 18 Step 4.

- [ ] **Step 4: Swap strings in pages**

In `modules/dashboard/dashboard/pages/*.tsx`, import `useT` and swap literals for `t('dashboard.home.title')`, etc.

- [ ] **Step 5: Run tests**

```bash
uv run pytest modules/dashboard/tests -v
```

- [ ] **Step 6: Commit**

```bash
git add modules/dashboard
git commit -m "feat(dashboard): localize page strings"
```

---

## Task 20: Extract strings from `modules/products` + host landing/error

**Files:**
- Create: `modules/products/products/locales/en.json`
- Create: `modules/products/products/locales/es.json`
- Modify: `modules/products/products/module.py`
- Modify: `modules/products/products/pages/Browse.tsx`
- Modify: `modules/products/products/pages/Create.tsx`
- Modify: `modules/products/products/pages/Edit.tsx`
- Modify: `modules/products/products/pages/validation.ts`
- Create: `host/locales/en.json`
- Create: `host/locales/es.json`
- Modify: `host/client_app/pages/Landing.tsx`
- Modify: `host/client_app/pages/Error.tsx`

**Context:** Products is the biggest module with strings in 3 pages plus validation schemas. Host has Landing + Error pages.

- [ ] **Step 1: Create `modules/products/products/locales/en.json`**

Based on the strings already visible in `Browse.tsx` (lines 103, 121, 122, 129, 196-200, 226-230, 242):

```json
{
  "browse": {
    "title": "Products",
    "description": "Manage your product catalog",
    "new_button": "New Product",
    "search_placeholder": "Search products...",
    "count_one": "{count} product",
    "count_other": "{count} products",
    "empty_title": "No products yet",
    "empty_description": "Get started by creating your first product.",
    "create_button": "Create Product",
    "no_match": "No products match \"{query}\""
  },
  "table": {
    "name": "Name",
    "description": "Description",
    "price": "Price",
    "status": "Status",
    "actions": "Actions",
    "active": "Active",
    "inactive": "Inactive"
  },
  "delete_dialog": {
    "title": "Delete \"{name}\"?",
    "description": "This action cannot be undone. This will permanently delete the product from the catalog.",
    "cancel": "Cancel",
    "confirm": "Delete"
  },
  "toasts": {
    "deleted": "\"{name}\" deleted",
    "delete_failed": "Failed to delete product"
  },
  "validation": {
    "name_required": "Name is required",
    "price_positive": "Price must be greater than zero"
  }
}
```

- [ ] **Step 2: Create `modules/products/products/locales/es.json`**

Translate every key. Machine translation is fine for this initial commit.

- [ ] **Step 3: Add `locale_dirs()` to `ProductsModule`**

Edit `modules/products/products/module.py`. Add at top:

```python
import importlib.resources
from pathlib import Path
```

Add to the class:

```python
    def locale_dirs(self) -> dict[str, Path]:
        return {"products": Path(str(importlib.resources.files(__package__) / "locales"))}
```

- [ ] **Step 4: Swap strings in `Browse.tsx`**

Edit `modules/products/products/pages/Browse.tsx`. Add import:

```tsx
import { useT } from '@simple-module/i18n';
```

Inside the `Browse` function body, after the `usePage` destructure:

```tsx
  const { t } = useT();
```

Replace every literal with a `t()` call. Examples:

- `title="Products"` → `title={t('products.browse.title')}`
- `description="Manage your product catalog"` → `description={t('products.browse.description')}`
- `"Search products..."` → `t('products.browse.search_placeholder')`
- The pluralized count line (lines 128-130) becomes:
  ```tsx
  {pagination.total > 0 && (
    <p className="text-sm text-muted-foreground whitespace-nowrap">
      {t('products.browse.count', { count: pagination.total })}
    </p>
  )}
  ```
- Column headers → `t('products.table.name')`, etc.
- Badge text `'Active'`/`'Inactive'` → `t('products.table.active')` / `t('products.table.inactive')`
- AlertDialog title → `t('products.delete_dialog.title', { name: product.name })`
- Description → `t('products.delete_dialog.description')`
- Cancel/Delete buttons → `t('products.delete_dialog.cancel')` / `t('products.delete_dialog.confirm')`
- Toast messages in `handleDelete`:
  ```tsx
  onSuccess: () => toast.success(t('products.toasts.deleted', { name: product.name })),
  onError: () => toast.error(t('products.toasts.delete_failed')),
  ```
- Empty state copy → `t('products.browse.empty_title')`, `t('products.browse.empty_description')`, `t('products.browse.create_button')`
- No-match copy → `t('products.browse.no_match', { query: search })`

- [ ] **Step 5: Swap strings in `Create.tsx` and `Edit.tsx`**

Same pattern as Step 4 for each file. Read the file first, inventory strings, add `useT`, swap.

- [ ] **Step 6: Convert `validation.ts` to a hook**

Edit `modules/products/products/pages/validation.ts`. If it currently exports a plain schema, wrap it:

```ts
import { useT } from '@simple-module/i18n';
import { z } from 'zod';

export function useProductSchema() {
  const { t } = useT();
  return z.object({
    name: z.string().min(1, t('products.validation.name_required')),
    price: z.coerce.number().positive(t('products.validation.price_positive')),
  });
}
```

Update callers in `Create.tsx` and `Edit.tsx` to call `useProductSchema()` inside the component.

- [ ] **Step 7: Create `host/locales/en.json`**

Inventory strings from `host/client_app/pages/Landing.tsx` (8.8 KB) and `Error.tsx`. Example skeleton:

```json
{
  "landing": {
    "hero_title": "Build modular apps in Python",
    "hero_subtitle": "Plugin modules that compose at boot.",
    "cta_login": "Sign in",
    "cta_learn_more": "Learn more"
  },
  "error": {
    "500_title": "Something went wrong",
    "500_description": "We've been notified and will investigate.",
    "404_title": "Page not found",
    "404_description": "The page you're looking for doesn't exist."
  }
}
```

Fill in the actual strings from the pages — do not leave placeholder wording.

- [ ] **Step 8: Create `host/locales/es.json`**

Spanish counterparts.

- [ ] **Step 9: Swap strings in `Landing.tsx` and `Error.tsx`**

Same pattern as Step 4.

- [ ] **Step 10: Run all tests**

```bash
uv run pytest -q
npm test
```

Expected: all green. If pytest complains that Products endpoints broke, check that tests aren't asserting against English literals that you removed.

- [ ] **Step 11: Commit**

```bash
git add modules/products host/locales host/client_app/pages
git commit -m "feat: localize products module, landing, and error pages"
```

---

## Task 21: Update scaffolder to generate localized modules

**Files:**
- Modify: `scripts/new_module.py`
- Modify: `scripts/_templates_py.py`
- Modify: `scripts/_templates_tsx.py`

**Context:** A freshly scaffolded module should be localizable from day one. Emit `locales/en.json` and have templates reference `useT()` / `TranslatorDep`.

- [ ] **Step 1: Read the existing templates**

```bash
head -80 scripts/_templates_py.py scripts/_templates_tsx.py
```

Understand the current placeholder substitution pattern (likely `.format()` or `{name}` replacements).

- [ ] **Step 2: Add `locale_dirs()` to the module.py template**

Edit `scripts/_templates_py.py`. In `module_py(ctx)`, add:
1. At the top of the imports block, add `import importlib.resources` and `from pathlib import Path` (if not already present).
2. Inside the class body, after `register_routes`, add:

```python
    def locale_dirs(self) -> dict[str, Path]:
        return {{"{pkg}": Path(str(importlib.resources.files(__package__) / "locales"))}}
```

Use the existing template's placeholder style (verify by reading the file first).

- [ ] **Step 3: Create a locale template function**

In `scripts/_templates_py.py`, add a new function near the bottom:

```python
def locales_en_json(ctx: ScaffoldContext) -> str:
    return """\
{
  "browse": {
    "title": "%s",
    "description": "Manage your %s",
    "new_button": "New %s",
    "search_placeholder": "Search %s...",
    "empty_title": "No %s yet",
    "empty_description": "Get started by creating your first %s.",
    "create_button": "Create %s"
  },
  "table": {
    "actions": "Actions"
  },
  "toasts": {
    "created": "%s created",
    "updated": "%s updated",
    "deleted": "%s deleted"
  }
}
""" % (
        ctx.class_name,  # title
        ctx.name,        # description plural
        ctx.singular_class,  # new button
        ctx.name,        # search placeholder
        ctx.name,        # empty title
        ctx.singular,    # empty description
        ctx.singular_class,  # create button
        ctx.singular_class,  # toast created
        ctx.singular_class,  # toast updated
        ctx.singular_class,  # toast deleted
    )
```

- [ ] **Step 4: Update the scaffolder to emit locales**

Edit `scripts/new_module.py`. Import the new template:

```python
from _templates_py import (
    ScaffoldContext,
    deps_py,
    locales_en_json,
    models_py,
    module_py,
    package_init,
    pyproject_toml,
    service_py,
)
```

In `scaffold_module`, after the `create_file(src_dir / "pages" / "Edit.tsx", ...)` line (around line 111), add:

```python
    create_file(src_dir / "locales" / "en.json", locales_en_json(ctx))
```

- [ ] **Step 5: Update the TSX templates to use `useT()`**

Edit `scripts/_templates_tsx.py`. For each of `browse_tsx`, `create_tsx`, `edit_tsx`:

1. Add import `import { useT } from '@simple-module/i18n';`
2. Inside the component, add `const { t } = useT();` as the first line after props destructuring.
3. Swap hardcoded strings for `t('<pkg>.<area>.<key>')` — e.g. `title="{ctx.class_name}"` becomes `title={{t('{ctx.pkg}.browse.title')}}` (in the template's placeholder-aware syntax).

Be conservative: only swap strings that have matching keys in the `locales_en_json` template above. Anything without a corresponding key can stay hardcoded (the module author will extract it later).

- [ ] **Step 6: Sanity-check by scaffolding a throwaway module**

```bash
python scripts/new_module.py test_scaffold_123
ls modules/test_scaffold_123/test_scaffold_123/locales
cat modules/test_scaffold_123/test_scaffold_123/locales/en.json
grep -c "useT" modules/test_scaffold_123/test_scaffold_123/pages/Browse.tsx
```

Expected: `locales/en.json` exists; `useT` appears in Browse/Create/Edit.

Clean up:

```bash
rm -rf modules/test_scaffold_123
# Revert changes to host/pyproject.toml and pyproject.toml:
git checkout host/pyproject.toml pyproject.toml
```

- [ ] **Step 7: Commit**

```bash
git add scripts/new_module.py scripts/_templates_py.py scripts/_templates_tsx.py
git commit -m "feat(scaffolder): generate locales/en.json and t()-using pages"
```

---

## Task 22: Documentation

**Files:**
- Modify: `docs/framework-conventions.md`
- Modify: `README.md`

**Context:** Module authors need a single place to learn the i18n conventions. Keep it concise.

- [ ] **Step 1: Append Internationalization section to `framework-conventions.md`**

Add at the bottom:

```markdown
## Internationalization

Modules ship translations as JSON under `<package>/locales/<lang>.json` and
declare them via `ModuleBase.locale_dirs()`:

```python
def locale_dirs(self) -> dict[str, Path]:
    return {"orders": importlib.resources.files(__package__) / "locales"}
```

### Key naming

Keys are namespaced by the module and hierarchical by area. Convention:
`<namespace>.<area>.<string>` — e.g. `orders.browse.title`. Use snake_case
for leaves.

### Interpolation

Placeholders use `{name}` syntax:

```json
{ "greeting": "Hello, {name}" }
```

```tsx
t('orders.greeting', { name: user.name })
```

```python
t.t("orders.greeting", name=user.name)
```

Missing placeholders are left as `{name}` rather than raising.

### Pluralization

Suffix keys with CLDR categories (`_zero`, `_one`, `_two`, `_few`, `_many`,
`_other`); only `_other` is required. Pass `count` as a param:

```json
{
  "items_one": "{count} item",
  "items_other": "{count} items"
}
```

```tsx
t('orders.items', { count: items.length })
```

Backend uses Babel's CLDR plural rules; frontend uses i18next's `Intl.PluralRules`
— both follow the same CLDR categories, so behavior matches.

### Validation messages

Validation messages must be constructed *inside* a React hook so they
pick up the active locale:

```ts
export function useProductSchema() {
  const { t } = useT();
  return z.object({ name: z.string().min(1, t('products.validation.name_required')) });
}
```

Do NOT declare `const schema = z.object({ ... t('...') })` at module scope —
it will resolve against whatever locale was active at first render, forever.

### Host and shared-package strings

- Host strings (landing page, error page) live in `host/locales/` and are
  namespaced `host.*`.
- Shared UI strings (`packages/ui/`) live in `packages/ui/locales/`,
  namespaced `ui.*`.

### Diagnostics

`make doctor` checks:

- **SM013:** missing locale file for a declared supported locale.
- **SM014:** non-default locale missing keys present in the default.
- **SM015:** non-default locale has keys not in the default.
- **SM016:** locale JSON fails to parse.

Warnings in dev; errors fail boot in production.

### Supported locales

Configure via env:

```
SM_I18N_DEFAULT_LOCALE=en
SM_I18N_SUPPORTED_LOCALES=en,es,de
SM_I18N_COOKIE_NAME=locale
```

Locales not in `SM_I18N_SUPPORTED_LOCALES` are rejected by the switcher
endpoint and ignored by `LocaleMiddleware`.
```

- [ ] **Step 2: Add bullet to `README.md`**

In the Architecture section of `README.md` (around line 110), add a bullet after the Diagnostics bullet:

```markdown
- **Internationalization**: per-module `locales/<lang>.json` files merged at boot into `I18nRegistry`. Frontend uses `i18next` with type-safe keys; backend uses `Babel` for CLDR plurals. Locale resolved per request via cookie → `Accept-Language` → `SM_I18N_DEFAULT_LOCALE`. See `framework-conventions.md` → Internationalization.
```

Add to the "Common commands" table if relevant (no new command needed — `make doctor` covers it).

- [ ] **Step 3: Commit**

```bash
git add docs/framework-conventions.md README.md
git commit -m "docs: document i18n conventions and settings"
```

---

## Task 23: End-to-end smoke verification

**Files:** None (verification-only task).

**Context:** Boot the app, click through the flow, make sure every part works together. This is the final gate before calling the feature done.

- [ ] **Step 1: Set up `.env` with a second locale**

Ensure `.env` has:

```
SM_I18N_DEFAULT_LOCALE=en
SM_I18N_SUPPORTED_LOCALES=["en","es"]
```

(The JSON-list format is what pydantic-settings parses for list fields.)

- [ ] **Step 2: Start the dev servers**

```bash
make kill  # ensure clean slate
make dev
```

Wait for both API and Vite to report ready.

- [ ] **Step 3: Verify `generated-resources.ts` was emitted**

```bash
head -30 host/client_app/generated-resources.ts
wc -l host/client_app/generated-resources.ts
```

Expected: populated file with a large key set (not the empty stub). Count should be ~40-200 lines depending on how many strings were extracted.

- [ ] **Step 4: Check typecheck now sees real keys**

```bash
# Introduce a typo somewhere temporarily to verify narrowing works.
# Example: edit modules/products/products/pages/Browse.tsx to call
#   t('products.browse.titel') instead of 'title'.
npx tsc --noEmit -p host/client_app/tsconfig.json
```

Expected: TypeScript reports an error on the typo. Revert the typo.

- [ ] **Step 5: Browser smoke**

Open `http://localhost:8000`:

1. Land on `/` in English.
2. Switcher visible in top-right; pick "Español".
3. Page reloads, strings are Spanish.
4. Log in → navigate to `/dashboard`, then `/products`. All strings Spanish.
5. Refresh browser — still Spanish (cookie is persisted with long expiry).
6. Open DevTools Network → confirm Inertia responses include `props.i18n.locale === "es"`.

- [ ] **Step 6: Run diagnostics**

```bash
make doctor
```

Expected: no SM013/SM014/SM015/SM016 findings. Any warnings should be addressed before declaring done.

- [ ] **Step 7: Run full test suite**

```bash
make test      # pytest + vitest
make lint
```

Expected: all green.

- [ ] **Step 8: Commit (only if any fixes were needed)**

If you had to fix anything during smoke, commit it with a descriptive message. If everything passed first try, no commit needed.

```bash
# Example if you had to fix a missing key:
git add <files>
git commit -m "fix(i18n): add missing dashboard welcome key"
```

- [ ] **Step 9: Final cleanup**

Check for any straggler TODO/FIXME comments introduced during the work:

```bash
grep -rn "TODO\|FIXME\|XXX" framework/core/simple_module_core/i18n.py \
                              framework/hosting/simple_module_hosting/i18n_*.py \
                              host/routes_i18n.py \
                              packages/i18n packages/ui/src/components/LocaleSwitcher.tsx
```

Expected: no findings.

---

## Acceptance Criteria (from spec — verify at end)

- [ ] All of `modules/auth`, `modules/dashboard`, `modules/products`, `host/`, `packages/ui/` have their user-facing strings in `locales/en.json` and `locales/es.json`.
- [ ] `t('products.browse.title')` works in React; an unknown key is a TS compile error (after the backend boots and emits `generated-resources.ts`).
- [ ] `t.t("auth.errors.invalid_credentials")` works in FastAPI endpoints via `TranslatorDep`.
- [ ] `POST /i18n/set-locale` with `locale=es` sets the cookie and subsequent loads are Spanish.
- [ ] Inertia shared props include `{locale, supportedLocales, messages}` on every page.
- [ ] `make doctor` reports no i18n issues.
- [ ] `make test` (pytest + Vitest) passes.
- [ ] `make new-module name=orders` produces a module whose pages use `useT()` and whose `locales/en.json` matches the scaffolded template strings.
- [ ] `framework-conventions.md` has an Internationalization section.
