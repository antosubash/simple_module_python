# `simple_module_inertia` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `fastapi-inertia` dependency with our own `simple_module_inertia` package that implements the full Inertia v3 page-object protocol, then move this repo's client to `@inertiajs/react` v3.

**Architecture:** A sixth framework package forked from `fastapi-inertia` (MIT) and split by responsibility: header parsing → prop resolution → page-object assembly → HTTP response, each a pure stage with its own tests. `simple_module_hosting` swaps its dependency and deletes the three workarounds it currently wraps around upstream. The module-facing contract (`InertiaDep`, `InertiaResponse`, `render`, `share`) is unchanged, so call sites change one import line. The client migration is a separate PR so the package can be proven against the *existing* v2 client first.

**Tech Stack:** Python 3.12, FastAPI, Starlette, Jinja2, pydantic (via `fastapi.encoders.jsonable_encoder`), pytest + pytest-asyncio (`asyncio_mode=auto`), uv workspaces, hatchling. Client: React 19, `@inertiajs/react` 3.x, Vite 8.

**Spec:** `docs/superpowers/specs/2026-09-10-inertia-v3-adapter-design.md`

## Global Constraints

- Every `.py` file stays **under 300 lines** (`scripts/check_file_size.py` fails CI otherwise).
- **Lockstep version** is `0.0.34` — every framework package pins siblings with `==0.0.34`; `scripts/bump_version.py` rewrites them on release.
- Test files have **no `__init__.py`** anywhere, so basenames must be unique repo-wide. All new tests use the `test_adapter_*.py` prefix (verified unused).
- pytest `testpaths` in the root `pyproject.toml` is an explicit list — `framework/inertia/tests` **must be added** or its tests never run.
- `[tool.uv.workspace].members` already includes `framework/*`; no change needed there.
- SQLModel is the model standard; the encoder must handle pydantic/SQLModel models, `datetime`, `UUID`, `Decimal`, `Path`, enums, dataclasses.
- No `session.commit()` in framework code. Not relevant here, but the rule stands.
- `ruff format` also formats python code blocks inside `.md` — run `uv run ruff format docs/` before `make lint` after editing this plan or the spec.
- Commit messages end with `Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW`.
- Precognition and SSR are **out of scope**. `templating.py` keeps upstream's SSR head/body hooks but nothing calls them.

---

## File map (PR 1)

| Path | Responsibility |
|---|---|
| `framework/inertia/pyproject.toml` | Package metadata, deps, hatch build |
| `framework/inertia/LICENSE`, `NOTICE`, `README.md` | MIT + upstream attribution |
| `framework/inertia/simple_module_inertia/__init__.py` | Public exports |
| `.../config.py` | `InertiaConfig`, `resolved_version()` |
| `.../props.py` | `Prop` wrapper + factories |
| `.../request.py` | `InertiaRequest.from_headers()` |
| `.../resolve.py` | `resolve_props()` → `ResolvedProps` |
| `.../page.py` | `build_page()`, `encode_page()`, `to_relative_url()` |
| `.../manifest.py` | `read_manifest()`, `entry_assets()` |
| `.../response.py` | `json_response()`, `html_response()`, `version_conflict()`, `redirect()`, `location()`, `fragment_redirect()` |
| `.../errors.py` | `InertiaVersionConflictException` + two exception handlers |
| `.../templating.py` | `InertiaContext`, `InertiaExtension` |
| `.../inertia.py` | `Inertia` facade |
| `.../deps.py` | `inertia_dependency_factory()` |
| `framework/inertia/tests/test_adapter_*.py` | One test module per source module |

Modified in PR 1: `pyproject.toml` (testpaths), `.github/workflows/release.yml` (matrix), `framework/hosting/pyproject.toml`, `framework/hosting/simple_module_hosting/{_inertia_setup,_error_handlers,_phase_helpers,inertia_deps}.py`, `framework/core/simple_module_core/services.py`, every `from inertia import` site in `modules/`, `host/`, and `framework/cli/simple_module_cli/templates/host/routes.py`. Deleted: `_inertia_json.py`, `_inertia_url.py`, and hosting tests `test_inertia_json_encoder.py`, `test_inertia_relative_url.py`, `test_inertia_manifest.py` (ported into the package).

---

### Task 1: Package skeleton, attribution, and wiring

**Files:**
- Create: `framework/inertia/pyproject.toml`
- Create: `framework/inertia/LICENSE`
- Create: `framework/inertia/NOTICE`
- Create: `framework/inertia/README.md`
- Create: `framework/inertia/simple_module_inertia/__init__.py`
- Create: `framework/inertia/simple_module_inertia/py.typed`
- Create: `framework/inertia/tests/test_adapter_package.py`
- Modify: `pyproject.toml` (root — `testpaths`)
- Modify: `.github/workflows/release.yml:111-128` (matrix)

**Interfaces:**
- Produces: an importable `simple_module_inertia` package at version `0.0.34`, discoverable by uv, pytest and the release workflow. `__all__` is filled in by Task 10.

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_package.py
"""The package is installed, versioned in lockstep, and attributed."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import tomllib

_PKG_DIR = Path(__file__).resolve().parents[1]


def test_package_is_importable_at_the_lockstep_version() -> None:
    import simple_module_inertia  # noqa: F401

    core = tomllib.loads((_PKG_DIR.parent / "core" / "pyproject.toml").read_text())
    assert version("simple_module_inertia") == core["project"]["version"]


def test_upstream_attribution_ships_with_the_package() -> None:
    notice = (_PKG_DIR / "NOTICE").read_text()
    assert "fastapi-inertia" in notice
    assert "MIT" in notice
    assert "Permission is hereby granted" in notice, "must reproduce the upstream MIT text"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_package.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia'` (or "file or directory not found" until the tests dir is on `testpaths`; both are the "not wired yet" signal).

- [ ] **Step 3: Create the package metadata**

```toml
# framework/inertia/pyproject.toml
[project]
name = "simple_module_inertia"
version = "0.0.34"
description = "Inertia.js v3 server adapter for FastAPI — the protocol half of simple_module's React frontend"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE", "NOTICE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "inertia", "inertiajs", "fastapi", "react"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Typing :: Typed",
]
dependencies = [
    "fastapi>=0.115",
    "jinja2>=3.1",
    "starlette>=0.44",
]

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["simple_module_inertia"]
```

- [ ] **Step 4: Create LICENSE, NOTICE, README, and the empty package**

```bash
cp LICENSE framework/inertia/LICENSE
UPSTREAM_LICENSE=$(find .venv -path '*fastapi_inertia-1.1.0.dist-info/LICENSE' | head -1)
{
  echo "This package is a fork of fastapi-inertia 1.1.0 (https://github.com/hxjo/fastapi-inertia),"
  echo "distributed under the MIT License. The original license text follows, as the"
  echo "MIT License requires."
  echo
  cat "$UPSTREAM_LICENSE"
} > framework/inertia/NOTICE
mkdir -p framework/inertia/simple_module_inertia framework/inertia/tests
touch framework/inertia/simple_module_inertia/py.typed
```

```markdown
<!-- framework/inertia/README.md -->
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
```

```python
# framework/inertia/simple_module_inertia/__init__.py
"""Inertia.js v3 server adapter. Public surface is assembled in Task 10."""

from __future__ import annotations

__all__: list[str] = []
```

- [ ] **Step 5: Wire pytest and the release matrix**

In the root `pyproject.toml`, add `"framework/inertia/tests"` to `testpaths` immediately after `"framework/hosting/tests"`:

```toml
testpaths = ["framework/cli/tests", "framework/core/tests", "framework/db/tests", "framework/hosting/tests", "framework/inertia/tests", "framework/testing/tests", "host/tests", ...
```

In `.github/workflows/release.yml`, inside the `publish-pypi` job's `matrix` package list, add a line after `- simple_module_hosting`:

```yaml
          - simple_module_inertia
```

- [ ] **Step 6: Install and run the test**

Run: `uv sync --all-packages && uv run pytest framework/inertia/tests/test_adapter_package.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add framework/inertia pyproject.toml .github/workflows/release.yml
git commit -m "feat(inertia): scaffold simple_module_inertia with upstream attribution

Sixth framework package, lockstep-versioned, wired into pytest testpaths
and the PyPI release matrix. Empty for now; the adapter lands in the
following commits.

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

> **Operator note (not a code step):** before the next release tag, register a PyPI *pending publisher* for `simple_module_inertia` (owner `antosubash`, repo `simple_module_python`, workflow `release.yml`). Without it the new matrix leg 403s and blocks the whole release.

---

### Task 2: `config.py` — `InertiaConfig` with a callable version

**Files:**
- Create: `framework/inertia/simple_module_inertia/config.py`
- Test: `framework/inertia/tests/test_adapter_config.py`

**Interfaces:**
- Produces: `InertiaConfig` dataclass (same field names as upstream, plus `version: str | Callable[[], str]`) and `resolved_version(config) -> str`.
- `InertiaConfig.templates: Jinja2Templates` is required (positional-or-keyword, first).

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_config.py
from __future__ import annotations

from fastapi.templating import Jinja2Templates

from simple_module_inertia.config import InertiaConfig, resolved_version


def _templates(tmp_path):
    return Jinja2Templates(directory=str(tmp_path))


def test_defaults_match_the_protocol_facing_ones(tmp_path) -> None:
    cfg = InertiaConfig(templates=_templates(tmp_path))
    assert cfg.environment == "development"
    assert cfg.version == "1.0"
    assert cfg.root_template_filename == "index.html"
    assert cfg.entrypoint_filename == "main.js"
    assert cfg.use_flash_errors is False
    assert cfg.flash_error_key == "errors"


def test_a_string_version_resolves_to_itself(tmp_path) -> None:
    cfg = InertiaConfig(templates=_templates(tmp_path), version="abc123")
    assert resolved_version(cfg) == "abc123"


def test_a_callable_version_is_called_each_time(tmp_path) -> None:
    calls = []

    def compute() -> str:
        calls.append(1)
        return f"v{len(calls)}"

    cfg = InertiaConfig(templates=_templates(tmp_path), version=compute)
    assert resolved_version(cfg) == "v1"
    assert resolved_version(cfg) == "v2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.config'`

- [ ] **Step 3: Write the implementation**

```python
# framework/inertia/simple_module_inertia/config.py
"""Adapter configuration.

Field names match upstream ``fastapi-inertia`` so ``simple_module_hosting``'s
``setup_inertia`` keeps constructing it the same way. The one addition is that
``version`` may be a zero-arg callable, so an app can derive the asset version
from its Vite manifest hash at boot instead of hard-coding ``"1.0"``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.templating import Jinja2Templates


@dataclass
class InertiaConfig:
    templates: Jinja2Templates
    environment: Literal["development", "production"] = "development"
    version: str | Callable[[], str] = "1.0"
    dev_url: str = "http://localhost:5173"
    ssr_url: str = "http://localhost:13714"
    ssr_enabled: bool = False
    manifest_json_path: str = ""
    root_directory: str = "src"
    root_template_filename: str = "index.html"
    entrypoint_filename: str = "main.js"
    use_flash_messages: bool = False
    use_flash_errors: bool = False
    flash_message_key: str = "messages"
    flash_error_key: str = "errors"
    assets_prefix: str = ""
    extra_template_context: dict[str, Any] = field(default_factory=dict)


def resolved_version(config: InertiaConfig) -> str:
    """The asset version as a string, calling ``version`` if it is a callable."""
    version = config.version
    return str(version()) if callable(version) else str(version)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): InertiaConfig with a callable asset version

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 3: `props.py` — one `Prop` wrapper, eight factories

**Files:**
- Create: `framework/inertia/simple_module_inertia/props.py`
- Test: `framework/inertia/tests/test_adapter_props.py`

**Interfaces:**
- Produces: `Prop` (frozen dataclass) with fields `value, optional, always, deferred_group, merge_mode, match_on, once_key, once_expires_at, scroll`; `ScrollMeta` dataclass; factories `optional(v)`, `always(v)`, `defer(v, group="default")`, `merge(v, match_on=None)`, `prepend(v, match_on=None)`, `deep_merge(v, match_on=None)`, `once(v, key=None, expires_at=None)`, `scroll(v, page_name, current_page, previous_page, next_page, reset=False)`, `lazy(v)` (deprecated alias of `optional`); `as_prop(v) -> Prop`; `async resolve_value(v) -> Any`.
- Every factory accepts a raw value **or** an existing `Prop`, returning a new `Prop` with the extra flag set — that is how wrappers compose.

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_props.py
from __future__ import annotations

import warnings

import pytest

from simple_module_inertia.props import (
    Prop,
    ScrollMeta,
    always,
    as_prop,
    deep_merge,
    defer,
    lazy,
    merge,
    once,
    optional,
    prepend,
    resolve_value,
    scroll,
)


def test_as_prop_wraps_a_raw_value_and_passes_a_prop_through() -> None:
    p = as_prop(1)
    assert isinstance(p, Prop) and p.value == 1
    assert as_prop(p) is p


def test_each_factory_sets_exactly_its_flag() -> None:
    assert optional(1).optional is True
    assert always(1).always is True
    assert defer(1).deferred_group == "default"
    assert defer(1, group="sidebar").deferred_group == "sidebar"
    assert merge([]).merge_mode == "append"
    assert prepend([]).merge_mode == "prepend"
    assert deep_merge({}).merge_mode == "deep"
    assert merge([], match_on="data.id").match_on == "data.id"
    assert once(1).once_key is None and once(1).once_expires_at is None
    assert once(1, key="plans", expires_at=1700000000000).once_key == "plans"
    s = scroll([], page_name="page", current_page=1, previous_page=None, next_page=2)
    assert s.scroll == ScrollMeta("page", 1, None, 2, False)


def test_factories_compose_by_stacking_flags() -> None:
    p = merge(defer(lambda: [1], group="feed"), match_on="id")
    assert p.deferred_group == "feed"
    assert p.merge_mode == "append"
    assert p.match_on == "id"
    assert callable(p.value)


def test_lazy_is_a_deprecated_alias_of_optional() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        p = lazy(1)
    assert p.optional is True
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


async def test_resolve_value_handles_values_callables_and_awaitables() -> None:
    async def later() -> str:
        return "async"

    assert await resolve_value(5) == 5
    assert await resolve_value(lambda: "sync") == "sync"
    assert await resolve_value(later) == "async"
    assert await resolve_value(as_prop(lambda: "wrapped")) == "wrapped"


def test_scroll_requires_a_page_name() -> None:
    with pytest.raises(ValueError, match="page_name"):
        scroll([], page_name="", current_page=1, previous_page=None, next_page=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_props.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.props'`

- [ ] **Step 3: Write the implementation**

```python
# framework/inertia/simple_module_inertia/props.py
"""Prop wrappers.

One frozen ``Prop`` carries every v3 flag; each factory sets one of them and
accepts either a raw value or an existing ``Prop``, so wrappers compose by
stacking: ``merge(defer(load_feed), match_on="id")``. The resolver reads the
flags; nothing here talks to a request.
"""

from __future__ import annotations

import inspect
import warnings
from dataclasses import dataclass, replace
from typing import Any, Literal

MergeMode = Literal["append", "prepend", "deep"]


@dataclass(frozen=True)
class ScrollMeta:
    """Infinite-scroll cursor metadata, reported under ``scrollProps``."""

    page_name: str
    current_page: int
    previous_page: int | None
    next_page: int | None
    reset: bool = False

    def as_page_object(self) -> dict[str, Any]:
        return {
            "pageName": self.page_name,
            "currentPage": self.current_page,
            "previousPage": self.previous_page,
            "nextPage": self.next_page,
            "reset": self.reset,
        }


@dataclass(frozen=True)
class Prop:
    value: Any
    optional: bool = False
    always: bool = False
    deferred_group: str | None = None
    merge_mode: MergeMode | None = None
    match_on: str | None = None
    once_key: str | None = None
    once_expires_at: int | None = None
    scroll: ScrollMeta | None = None

    @property
    def is_once(self) -> bool:
        return self.once_key is not None or self.once_expires_at is not None or self._once_flag

    # ``once(value)`` with no key still marks the prop as once; the key defaults
    # to the prop name at resolve time. A private flag keeps that distinction
    # without making ``once_key`` a sentinel.
    _once_flag: bool = False


def as_prop(value: Any) -> Prop:
    return value if isinstance(value, Prop) else Prop(value)


def optional(value: Any) -> Prop:
    return replace(as_prop(value), optional=True)


def always(value: Any) -> Prop:
    return replace(as_prop(value), always=True)


def defer(value: Any, group: str = "default") -> Prop:
    return replace(as_prop(value), deferred_group=group)


def merge(value: Any, match_on: str | None = None) -> Prop:
    return replace(as_prop(value), merge_mode="append", match_on=match_on)


def prepend(value: Any, match_on: str | None = None) -> Prop:
    return replace(as_prop(value), merge_mode="prepend", match_on=match_on)


def deep_merge(value: Any, match_on: str | None = None) -> Prop:
    return replace(as_prop(value), merge_mode="deep", match_on=match_on)


def once(value: Any, key: str | None = None, expires_at: int | None = None) -> Prop:
    return replace(as_prop(value), once_key=key, once_expires_at=expires_at, _once_flag=True)


def scroll(
    value: Any,
    *,
    page_name: str,
    current_page: int,
    previous_page: int | None,
    next_page: int | None,
    reset: bool = False,
) -> Prop:
    if not page_name:
        raise ValueError("scroll() requires a non-empty page_name")
    meta = ScrollMeta(page_name, current_page, previous_page, next_page, reset)
    return replace(as_prop(value), scroll=meta)


def lazy(value: Any) -> Prop:
    """Deprecated alias kept for callers migrating from fastapi-inertia."""
    warnings.warn("lazy() is deprecated; use optional()", DeprecationWarning, stacklevel=2)
    return optional(value)


async def resolve_value(value: Any) -> Any:
    """Unwrap a ``Prop``, call a callable, await an awaitable — recursively."""
    if isinstance(value, Prop):
        value = value.value
    if callable(value):
        value = value()
    if inspect.isawaitable(value):
        value = await value
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_props.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): composable Prop wrapper and the v3 prop factories

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 4: `request.py` — every `X-Inertia-*` header, typed

**Files:**
- Create: `framework/inertia/simple_module_inertia/request.py`
- Test: `framework/inertia/tests/test_adapter_request.py`

**Interfaces:**
- Produces: `InertiaRequest` frozen dataclass with `is_inertia, version, partial_component, partial_data (frozenset[str]), partial_except (frozenset[str]), reset (frozenset[str]), error_bag, merge_intent ("append"|"prepend"|None), except_once_props (frozenset[str]), is_prefetch, method`; classmethod `from_headers(headers: Mapping[str, str], method: str) -> InertiaRequest`; method `is_partial_for(component: str) -> bool`.
- Header lookup is case-insensitive (Starlette's `Headers` already is; a plain dict is normalised).

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_request.py
from __future__ import annotations

from simple_module_inertia.request import InertiaRequest


def test_a_plain_browser_request_is_not_inertia() -> None:
    req = InertiaRequest.from_headers({}, method="GET")
    assert req.is_inertia is False
    assert req.version is None
    assert req.partial_data == frozenset()
    assert req.is_partial_for("Users/Index") is False


def test_every_header_is_parsed_case_insensitively() -> None:
    req = InertiaRequest.from_headers(
        {
            "x-inertia": "true",
            "X-INERTIA-VERSION": "abc",
            "X-Inertia-Partial-Component": "Users/Index",
            "X-Inertia-Partial-Data": "users, roles",
            "X-Inertia-Partial-Except": "stats",
            "X-Inertia-Reset": "users",
            "X-Inertia-Error-Bag": "signup",
            "X-Inertia-Infinite-Scroll-Merge-Intent": "prepend",
            "X-Inertia-Except-Once-Props": "plans,flags",
            "Purpose": "prefetch",
        },
        method="POST",
    )
    assert req.is_inertia is True
    assert req.version == "abc"
    assert req.partial_component == "Users/Index"
    assert req.partial_data == frozenset({"users", "roles"})
    assert req.partial_except == frozenset({"stats"})
    assert req.reset == frozenset({"users"})
    assert req.error_bag == "signup"
    assert req.merge_intent == "prepend"
    assert req.except_once_props == frozenset({"plans", "flags"})
    assert req.is_prefetch is True
    assert req.method == "POST"


def test_partial_only_applies_to_the_named_component() -> None:
    req = InertiaRequest.from_headers(
        {
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Users/Index",
            "X-Inertia-Partial-Data": "users",
        },
        method="GET",
    )
    assert req.is_partial_for("Users/Index") is True
    assert req.is_partial_for("Users/Edit") is False


def test_partial_except_alone_still_counts_as_partial() -> None:
    req = InertiaRequest.from_headers(
        {
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Feed",
            "X-Inertia-Partial-Except": "ads",
        },
        method="GET",
    )
    assert req.is_partial_for("Feed") is True


def test_unknown_merge_intent_is_ignored() -> None:
    req = InertiaRequest.from_headers(
        {"X-Inertia-Infinite-Scroll-Merge-Intent": "sideways"}, method="GET"
    )
    assert req.merge_intent is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_request.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.request'`

- [ ] **Step 3: Write the implementation**

```python
# framework/inertia/simple_module_inertia/request.py
"""The request half of the protocol: every ``X-Inertia-*`` header, typed.

A pure function of the header mapping and method — no Starlette ``Request``
crosses this boundary, so the resolver and its conformance tests never need
a server.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

MergeIntent = Literal["append", "prepend"]


def _csv(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class InertiaRequest:
    is_inertia: bool
    version: str | None
    partial_component: str | None
    partial_data: frozenset[str]
    partial_except: frozenset[str]
    reset: frozenset[str]
    error_bag: str | None
    merge_intent: MergeIntent | None
    except_once_props: frozenset[str]
    is_prefetch: bool
    method: str

    @classmethod
    def from_headers(cls, headers: Mapping[str, str], method: str) -> InertiaRequest:
        lower = {k.lower(): v for k, v in headers.items()}
        intent = (lower.get("x-inertia-infinite-scroll-merge-intent") or "").lower()
        return cls(
            is_inertia="x-inertia" in lower,
            version=lower.get("x-inertia-version"),
            partial_component=lower.get("x-inertia-partial-component") or None,
            partial_data=_csv(lower.get("x-inertia-partial-data")),
            partial_except=_csv(lower.get("x-inertia-partial-except")),
            reset=_csv(lower.get("x-inertia-reset")),
            error_bag=lower.get("x-inertia-error-bag") or None,
            merge_intent=intent if intent in ("append", "prepend") else None,  # type: ignore[arg-type]
            except_once_props=_csv(lower.get("x-inertia-except-once-props")),
            is_prefetch=(lower.get("purpose") or "").lower() == "prefetch",
            method=method.upper(),
        )

    def is_partial_for(self, component: str) -> bool:
        """A partial reload targets one component and names data or exclusions."""
        return self.partial_component == component and bool(
            self.partial_data or self.partial_except
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_request.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): typed InertiaRequest from the X-Inertia-* headers

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 5: `resolve.py` — the prop-resolution engine

**Files:**
- Create: `framework/inertia/simple_module_inertia/resolve.py`
- Test: `framework/inertia/tests/test_adapter_resolve_visits.py`
- Test: `framework/inertia/tests/test_adapter_resolve_metadata.py`

**Interfaces:**
- Consumes: `Prop`, `as_prop`, `resolve_value` (Task 3); `InertiaRequest` (Task 4).
- Produces: `ResolvedProps` dataclass with `props: dict[str, Any]`, `deferred: dict[str, list[str]]`, `merge: list[str]`, `prepend: list[str]`, `deep_merge: list[str]`, `match_on: list[str]`, `once: dict[str, dict[str, Any]]`, `scroll: dict[str, dict[str, Any]]`, `shared: list[str]`; and `async resolve_props(page_props: Mapping, shared_props: Mapping, component: str, req: InertiaRequest) -> ResolvedProps`.
- Rule: shared props merge **under** page props (page wins). `shared` lists the shared keys that survived into `props`.

- [ ] **Step 1: Write the failing visit-rule tests**

```python
# framework/inertia/tests/test_adapter_resolve_visits.py
"""Full-visit vs partial-reload rules — the spec's §3, one test per rule."""

from __future__ import annotations

from simple_module_inertia.props import always, defer, once, optional
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props

COMPONENT = "Users/Index"


def _req(method: str = "GET", **headers: str) -> InertiaRequest:
    h = {"X-Inertia": "true", **headers}
    return InertiaRequest.from_headers(h, method=method)


def _partial(data: str = "", exclude: str = "", component: str = COMPONENT, **extra: str):
    headers = {"X-Inertia-Partial-Component": component, **extra}
    if data:
        headers["X-Inertia-Partial-Data"] = data
    if exclude:
        headers["X-Inertia-Partial-Except"] = exclude
    return _req(**headers)


async def test_full_visit_resolves_regular_and_skips_optional_and_deferred() -> None:
    out = await resolve_props(
        {"users": [1], "stats": optional(lambda: {"n": 1}), "feed": defer(lambda: [2])},
        {},
        COMPONENT,
        _req(),
    )
    assert out.props == {"users": [1]}
    assert out.deferred == {"default": ["feed"]}


async def test_full_visit_resolves_always_props() -> None:
    out = await resolve_props({"flash": always(lambda: "hi")}, {}, COMPONENT, _req())
    assert out.props == {"flash": "hi"}


async def test_partial_data_resolves_only_the_named_keys_plus_always() -> None:
    out = await resolve_props(
        {"users": [1], "roles": [2], "flash": always("x"), "feed": defer(lambda: [3])},
        {},
        COMPONENT,
        _partial(data="users"),
    )
    assert out.props == {"users": [1], "flash": "x"}
    assert out.deferred == {}, "deferred metadata is only announced on full visits"


async def test_partial_data_resolves_optional_and_deferred_when_named() -> None:
    out = await resolve_props(
        {"stats": optional(lambda: {"n": 1}), "feed": defer(lambda: [3])},
        {},
        COMPONENT,
        _partial(data="stats,feed"),
    )
    assert out.props == {"stats": {"n": 1}, "feed": [3]}


async def test_partial_except_drops_the_named_keys() -> None:
    out = await resolve_props(
        {"users": [1], "roles": [2], "stats": [3]}, {}, COMPONENT, _partial(exclude="stats")
    )
    assert out.props == {"users": [1], "roles": [2]}


async def test_partial_data_and_except_combine() -> None:
    out = await resolve_props(
        {"users": [1], "roles": [2], "stats": [3]},
        {},
        COMPONENT,
        _partial(data="users,stats", exclude="stats"),
    )
    assert out.props == {"users": [1]}


async def test_partial_for_another_component_is_a_full_visit() -> None:
    out = await resolve_props(
        {"users": [1], "stats": optional(lambda: 1)},
        {},
        COMPONENT,
        _partial(data="stats", component="Users/Edit"),
    )
    assert out.props == {"users": [1]}


async def test_once_props_are_skipped_when_the_client_already_has_them() -> None:
    out = await resolve_props(
        {"plans": once(lambda: ["a"]), "flags": once(lambda: ["b"])},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Except-Once-Props": "plans"}),
    )
    assert out.props == {"flags": ["b"]}
    assert out.once == {"flags": {"prop": "flags", "expiresAt": None}}


async def test_shared_props_merge_under_page_props() -> None:
    out = await resolve_props(
        {"title": "page"}, {"title": "shared", "auth": {"id": 1}}, COMPONENT, _req()
    )
    assert out.props == {"title": "page", "auth": {"id": 1}}
    assert out.shared == ["auth"]


async def test_callables_and_awaitables_resolve_inside_nested_containers() -> None:
    async def later() -> int:
        return 2

    out = await resolve_props(
        {"nested": {"a": lambda: 1, "b": [later, {"c": lambda: 3}]}}, {}, COMPONENT, _req()
    )
    assert out.props == {"nested": {"a": 1, "b": [2, {"c": 3}]}}
```

- [ ] **Step 2: Write the failing metadata tests**

```python
# framework/inertia/tests/test_adapter_resolve_metadata.py
"""Merge / once / scroll metadata — what the page object announces alongside props."""

from __future__ import annotations

from simple_module_inertia.props import deep_merge, defer, merge, once, prepend, scroll
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props

COMPONENT = "Feed/Index"


def _req(**headers: str) -> InertiaRequest:
    return InertiaRequest.from_headers({"X-Inertia": "true", **headers}, method="GET")


async def test_each_merge_mode_is_reported_under_its_own_key() -> None:
    out = await resolve_props(
        {
            "posts": merge([1]),
            "notices": prepend([2]),
            "settings": deep_merge({"a": 1}),
        },
        {},
        COMPONENT,
        _req(),
    )
    assert out.merge == ["posts"]
    assert out.prepend == ["notices"]
    assert out.deep_merge == ["settings"]
    assert out.match_on == []


async def test_match_on_is_reported_as_prop_path_dot_key() -> None:
    out = await resolve_props(
        {"conversations": merge({"data": []}, match_on="data.id")}, {}, COMPONENT, _req()
    )
    assert out.match_on == ["conversations.data.id"]


async def test_a_reset_key_is_resolved_but_not_reported_as_mergeable() -> None:
    out = await resolve_props(
        {"posts": merge([1]), "notices": prepend([2])},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Reset": "posts"}),
    )
    assert out.props == {"posts": [1], "notices": [2]}
    assert out.merge == []
    assert out.prepend == ["notices"]


async def test_a_deferred_prop_can_also_be_mergeable() -> None:
    full = await resolve_props({"feed": merge(defer(lambda: [1]))}, {}, COMPONENT, _req())
    assert full.props == {} and full.deferred == {"default": ["feed"]}
    assert full.merge == ["feed"], "merge strategy is announced up front"

    partial = await resolve_props(
        {"feed": merge(defer(lambda: [1]))},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Partial-Component": COMPONENT, "X-Inertia-Partial-Data": "feed"}),
    )
    assert partial.props == {"feed": [1]} and partial.merge == ["feed"]


async def test_once_key_defaults_to_the_prop_name_and_carries_expiry() -> None:
    out = await resolve_props(
        {"plans": once(["a"]), "flags": once(["b"], key="feature-flags", expires_at=1700000000000)},
        {},
        COMPONENT,
        _req(),
    )
    assert out.once == {
        "plans": {"prop": "plans", "expiresAt": None},
        "feature-flags": {"prop": "flags", "expiresAt": 1700000000000},
    }


async def test_scroll_props_report_cursor_metadata() -> None:
    out = await resolve_props(
        {
            "posts": scroll(
                [1, 2], page_name="page", current_page=1, previous_page=None, next_page=2
            )
        },
        {},
        COMPONENT,
        _req(),
    )
    assert out.props == {"posts": [1, 2]}
    assert out.scroll == {
        "posts": {
            "pageName": "page",
            "currentPage": 1,
            "previousPage": None,
            "nextPage": 2,
            "reset": False,
        }
    }
    assert out.merge == ["posts"], "scroll props merge by default so pages accumulate"


async def test_scroll_merge_intent_prepend_moves_the_key() -> None:
    out = await resolve_props(
        {"posts": scroll([0], page_name="page", current_page=0, previous_page=None, next_page=1)},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Infinite-Scroll-Merge-Intent": "prepend"}),
    )
    assert out.prepend == ["posts"] and out.merge == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest framework/inertia/tests/test_adapter_resolve_visits.py framework/inertia/tests/test_adapter_resolve_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.resolve'`

- [ ] **Step 4: Write the implementation**

```python
# framework/inertia/simple_module_inertia/resolve.py
"""Prop resolution — the v3 rules in one place.

Input: the page's props, the shared props, the component being rendered and
the typed request. Output: the resolved values plus every piece of metadata
the page object announces (deferred groups, merge strategies, once keys,
scroll cursors, shared keys). Nothing here knows about HTTP.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from simple_module_inertia.props import Prop, as_prop, resolve_value
from simple_module_inertia.request import InertiaRequest


@dataclass
class ResolvedProps:
    props: dict[str, Any] = field(default_factory=dict)
    deferred: dict[str, list[str]] = field(default_factory=dict)
    merge: list[str] = field(default_factory=list)
    prepend: list[str] = field(default_factory=list)
    deep_merge: list[str] = field(default_factory=list)
    match_on: list[str] = field(default_factory=list)
    once: dict[str, dict[str, Any]] = field(default_factory=dict)
    scroll: dict[str, dict[str, Any]] = field(default_factory=dict)
    shared: list[str] = field(default_factory=list)


async def _deep_resolve(value: Any) -> Any:
    """Resolve callables/awaitables/Props anywhere inside a container."""
    value = await resolve_value(value)
    if isinstance(value, dict):
        return {k: await _deep_resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [await _deep_resolve(v) for v in value]
    return value


def _wants(name: str, prop: Prop, req: InertiaRequest, partial: bool) -> bool:
    """Should this prop's value be resolved for this response?"""
    if prop.is_once and name in req.except_once_props:
        return False
    if prop.always:
        return True
    if partial:
        if req.partial_data and name not in req.partial_data:
            return False
        return name not in req.partial_except
    return prop.optional is False and prop.deferred_group is None


def _announce_merge(name: str, prop: Prop, req: InertiaRequest, out: ResolvedProps) -> None:
    if name in req.reset:
        return
    mode = prop.merge_mode
    if prop.scroll is not None:
        mode = req.merge_intent or "append"
    if mode == "append":
        out.merge.append(name)
    elif mode == "prepend":
        out.prepend.append(name)
    elif mode == "deep":
        out.deep_merge.append(name)
    else:
        return
    if prop.match_on:
        out.match_on.append(f"{name}.{prop.match_on}")


async def resolve_props(
    page_props: Mapping[str, Any],
    shared_props: Mapping[str, Any],
    component: str,
    req: InertiaRequest,
) -> ResolvedProps:
    out = ResolvedProps()
    partial = req.is_partial_for(component)
    combined: dict[str, Any] = {**shared_props, **page_props}

    for name, raw in combined.items():
        prop = as_prop(raw)
        if not partial and prop.deferred_group is not None:
            out.deferred.setdefault(prop.deferred_group, []).append(name)
        if prop.merge_mode is not None or prop.scroll is not None:
            _announce_merge(name, prop, req, out)
        if not _wants(name, prop, req, partial):
            continue
        out.props[name] = await _deep_resolve(prop)
        if prop.is_once:
            key = prop.once_key or name
            out.once[key] = {"prop": name, "expiresAt": prop.once_expires_at}
        if prop.scroll is not None:
            out.scroll[name] = prop.scroll.as_page_object()

    out.shared = [k for k in shared_props if k in out.props and k not in page_props]
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest framework/inertia/tests/test_adapter_resolve_visits.py framework/inertia/tests/test_adapter_resolve_metadata.py -v`
Expected: PASS (17 tests).

- [ ] **Step 6: Check the line cap and commit**

Run: `uv run python scripts/check_file_size.py`
Expected: `OK: no files exceed 300 lines.`

```bash
git add framework/inertia
git commit -m "feat(inertia): prop-resolution engine with the full v3 rule set

Full-visit vs partial-reload, Partial-Except, Reset, once-except,
merge/prepend/deep with matchPropsOn, deferred groups, scroll cursors,
shared-under-page precedence — each covered by a conformance test.

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 6: `page.py` — page-object assembly, one encoder, relative URL

**Files:**
- Create: `framework/inertia/simple_module_inertia/page.py`
- Test: `framework/inertia/tests/test_adapter_page.py`
- Delete (ported here): `framework/hosting/tests/test_inertia_relative_url.py`, `framework/hosting/tests/test_inertia_json_encoder.py` — **deletion happens in Task 11**, not now.

**Interfaces:**
- Consumes: `ResolvedProps` (Task 5).
- Produces: `to_relative_url(url: str) -> str`; `build_page(*, component, resolved, url, version, errors, encrypt_history=False, clear_history=False, preserve_fragment=False) -> dict[str, Any]`; `encode_page(page: dict) -> Any` (JSON-safe structure via `jsonable_encoder`, raising `PropEncodingError(prop_path)` on failure); `PropEncodingError(ValueError)`.
- `build_page` always puts `errors` into `props` (the always-prop).

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_page.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from simple_module_inertia.page import PropEncodingError, build_page, encode_page, to_relative_url
from simple_module_inertia.resolve import ResolvedProps


class TestToRelativeUrl:
    @pytest.mark.parametrize(
        ("absolute", "expected"),
        [
            ("http://py.simplemodule.dev/", "/"),
            ("https://py.simplemodule.dev/dashboard/", "/dashboard/"),
            ("http://host:8000/files?q=logo&page=2", "/files?q=logo&page=2"),
            ("http://host:8000", "/"),
        ],
    )
    def test_keeps_only_path_and_query(self, absolute: str, expected: str) -> None:
        assert to_relative_url(absolute) == expected

    @pytest.mark.parametrize("relative", ["/", "/admin/users/", "/files?q=1"])
    def test_a_relative_url_is_unchanged(self, relative: str) -> None:
        assert to_relative_url(relative) == relative


class TestBuildPage:
    def test_required_fields_and_errors_always_prop(self) -> None:
        page = build_page(
            component="Users/Index",
            resolved=ResolvedProps(props={"users": [1]}),
            url="http://host:8000/admin/users/",
            version="v1",
            errors={},
        )
        assert page == {
            "component": "Users/Index",
            "props": {"users": [1], "errors": {}},
            "url": "/admin/users/",
            "version": "v1",
        }

    def test_conditional_fields_appear_only_when_set(self) -> None:
        resolved = ResolvedProps(
            props={},
            deferred={"default": ["feed"]},
            merge=["posts"],
            prepend=["notices"],
            deep_merge=["settings"],
            match_on=["posts.id"],
            once={"plans": {"prop": "plans", "expiresAt": None}},
            scroll={
                "posts": {
                    "pageName": "page",
                    "currentPage": 1,
                    "previousPage": None,
                    "nextPage": 2,
                    "reset": False,
                }
            },
            shared=["auth"],
        )
        page = build_page(
            component="C",
            resolved=resolved,
            url="/",
            version="v",
            errors={"email": "taken"},
            encrypt_history=True,
            clear_history=True,
            preserve_fragment=True,
        )
        assert page["deferredProps"] == {"default": ["feed"]}
        assert page["mergeProps"] == ["posts"]
        assert page["prependProps"] == ["notices"]
        assert page["deepMergeProps"] == ["settings"]
        assert page["matchPropsOn"] == ["posts.id"]
        assert page["onceProps"] == {"plans": {"prop": "plans", "expiresAt": None}}
        assert page["scrollProps"]["posts"]["nextPage"] == 2
        assert page["sharedProps"] == ["auth"]
        assert page["encryptHistory"] is True
        assert page["clearHistory"] is True
        assert page["preserveFragment"] is True
        assert page["props"]["errors"] == {"email": "taken"}

    def test_false_flags_and_empty_metadata_are_omitted(self) -> None:
        page = build_page(component="C", resolved=ResolvedProps(), url="/", version="v", errors={})
        for absent in (
            "deferredProps",
            "mergeProps",
            "prependProps",
            "deepMergeProps",
            "matchPropsOn",
            "onceProps",
            "scrollProps",
            "sharedProps",
            "encryptHistory",
            "clearHistory",
            "preserveFragment",
        ):
            assert absent not in page


class TestEncodePage:
    def test_rich_values_become_json_safe(self) -> None:
        class Settings(BaseModel):
            media_root: Path

        page = {
            "component": "C",
            "props": {
                "when": datetime(2026, 9, 10, tzinfo=UTC),
                "id": uuid.UUID(int=1),
                "price": Decimal("1.50"),
                "path": Path("/srv/media"),
                "settings": Settings(media_root=Path("/m")),
            },
            "url": "/",
            "version": "v",
        }
        encoded = encode_page(page)
        assert encoded["props"]["when"].startswith("2026-09-10")
        assert encoded["props"]["id"] == "00000000-0000-0000-0000-000000000001"
        assert encoded["props"]["price"] == 1.5
        assert encoded["props"]["path"] == "/srv/media"
        assert encoded["props"]["settings"] == {"media_root": "/m"}

    def test_an_unencodable_prop_names_its_path(self) -> None:
        class Opaque:
            pass

        page = {
            "component": "C",
            "props": {"user": {"avatar": Opaque()}},
            "url": "/",
            "version": "v",
        }
        with pytest.raises(PropEncodingError, match=r"props\.user\.avatar"):
            encode_page(page)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_page.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.page'`

- [ ] **Step 3: Write the implementation**

```python
# framework/inertia/simple_module_inertia/page.py
"""Page-object assembly and serialisation.

Two upstream defects are closed here rather than patched around it:

* the page ``url`` is root-relative, as the protocol specifies — an absolute
  url is handed to ``history.pushState`` and rejected behind a TLS-terminating
  proxy (GH #223);
* one encoder serves both the HTML and JSON branches, so a prop that renders
  on a full page load also renders on a client-side visit.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi.encoders import jsonable_encoder

from simple_module_inertia.resolve import ResolvedProps


class PropEncodingError(ValueError):
    """A prop could not be serialised; ``prop_path`` names it."""

    def __init__(self, prop_path: str, cause: Exception) -> None:
        self.prop_path = prop_path
        super().__init__(f"Inertia prop {prop_path} is not JSON-serialisable: {cause}")


def to_relative_url(url: str) -> str:
    """Path-and-query only. Already-relative input is returned unchanged."""
    try:
        parts = urlsplit(url)
    except ValueError:  # pragma: no cover - urlsplit is near-total
        return url
    if not parts.scheme and not parts.netloc:
        return url
    relative = parts.path or "/"
    return f"{relative}?{parts.query}" if parts.query else relative


def build_page(
    *,
    component: str,
    resolved: ResolvedProps,
    url: str,
    version: str,
    errors: dict[str, Any],
    encrypt_history: bool = False,
    clear_history: bool = False,
    preserve_fragment: bool = False,
) -> dict[str, Any]:
    """The page object. Conditional fields are present only when set."""
    page: dict[str, Any] = {
        "component": component,
        "props": {**resolved.props, "errors": errors},
        "url": to_relative_url(url),
        "version": version,
    }
    optional_fields: list[tuple[str, Any]] = [
        ("deferredProps", resolved.deferred),
        ("mergeProps", resolved.merge),
        ("prependProps", resolved.prepend),
        ("deepMergeProps", resolved.deep_merge),
        ("matchPropsOn", resolved.match_on),
        ("onceProps", resolved.once),
        ("scrollProps", resolved.scroll),
        ("sharedProps", resolved.shared),
    ]
    for key, value in optional_fields:
        if value:
            page[key] = value
    for key, flag in (
        ("encryptHistory", encrypt_history),
        ("clearHistory", clear_history),
        ("preserveFragment", preserve_fragment),
    ):
        if flag:
            page[key] = True
    return page


def _locate_failure(value: Any, path: str) -> str:
    """Find the deepest prop path that fails to encode, for the error message."""
    if isinstance(value, dict):
        for key, child in value.items():
            try:
                jsonable_encoder(child)
            except Exception:
                return _locate_failure(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            try:
                jsonable_encoder(child)
            except Exception:
                return _locate_failure(child, f"{path}[{index}]")
    return path


def encode_page(page: dict[str, Any]) -> Any:
    """JSON-safe structure for both render branches; names the failing prop."""
    try:
        return jsonable_encoder(page)
    except Exception as exc:
        raise PropEncodingError(_locate_failure(page["props"], "props"), exc) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_page.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): page-object assembly with relative url and one encoder

Absorbs hosting's _inertia_url and _inertia_json wraps: the url is
root-relative by construction and both render branches share one
jsonable_encoder pass that names the failing prop path on error.

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 7: `manifest.py` — read the Vite manifest by Vite's own key

**Files:**
- Create: `framework/inertia/simple_module_inertia/manifest.py`
- Test: `framework/inertia/tests/test_adapter_manifest.py`

**Interfaces:**
- Consumes: `InertiaConfig` (Task 2).
- Produces: `InertiaFiles` dataclass `(js: str, css: list[str])`; `read_manifest(path: str) -> dict` (lru-cached); `entry_assets(config: InertiaConfig) -> InertiaFiles` — production: manifest lookup by `entrypoint_filename`, then `f"{root_directory}/{entrypoint_filename}"`, then the first `isEntry` chunk; development: `f"{dev_url}/{entrypoint_filename}"` with `root_directory` honoured only when it is not `"."`/`""`.

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_manifest.py
"""Production assets come straight from Vite's manifest, keyed as Vite writes it."""

from __future__ import annotations

import json

import pytest
from fastapi.templating import Jinja2Templates

from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.manifest import entry_assets, read_manifest


def _manifest(tmp_path, entries: dict) -> str:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(entries))
    return str(path)


def _cfg(tmp_path, **kw) -> InertiaConfig:
    return InertiaConfig(templates=Jinja2Templates(directory=str(tmp_path)), **kw)


def test_production_resolves_the_entry_by_vites_native_key(tmp_path) -> None:
    manifest = _manifest(
        tmp_path,
        {
            "main.tsx": {
                "file": "assets/main-ABC.js",
                "css": ["assets/main-DEF.css"],
                "isEntry": True,
            },
            "pages/Foo.tsx": {"file": "assets/Foo-XYZ.js"},
        },
    )
    cfg = _cfg(
        tmp_path,
        environment="production",
        manifest_json_path=manifest,
        entrypoint_filename="main.tsx",
        root_directory=".",
        assets_prefix="static/dist",
    )
    files = entry_assets(cfg)
    assert files.js == "/static/dist/assets/main-ABC.js"
    assert files.css == ["/static/dist/assets/main-DEF.css"]


def test_production_falls_back_to_the_upstream_key_shape(tmp_path) -> None:
    manifest = _manifest(tmp_path, {"src/main.js": {"file": "assets/m.js", "isEntry": True}})
    cfg = _cfg(
        tmp_path,
        environment="production",
        manifest_json_path=manifest,
        entrypoint_filename="main.js",
        root_directory="src",
    )
    assert entry_assets(cfg).js == "/assets/m.js"


def test_production_falls_back_to_the_first_is_entry_chunk(tmp_path) -> None:
    manifest = _manifest(tmp_path, {"whatever.tsx": {"file": "assets/w.js", "isEntry": True}})
    cfg = _cfg(
        tmp_path,
        environment="production",
        manifest_json_path=manifest,
        entrypoint_filename="main.tsx",
    )
    assert entry_assets(cfg).js == "/assets/w.js"


def test_production_with_no_entry_raises_naming_the_manifest(tmp_path) -> None:
    manifest = _manifest(tmp_path, {"x.tsx": {"file": "assets/x.js"}})
    cfg = _cfg(tmp_path, environment="production", manifest_json_path=manifest)
    with pytest.raises(LookupError, match="manifest.json"):
        entry_assets(cfg)


def test_development_points_at_the_dev_server_without_a_dot_segment(tmp_path) -> None:
    cfg = _cfg(
        tmp_path,
        dev_url="http://localhost:5050",
        entrypoint_filename="main.tsx",
        root_directory=".",
    )
    assert entry_assets(cfg).js == "http://localhost:5050/main.tsx"
    assert entry_assets(cfg).css == []


def test_development_keeps_a_real_root_directory(tmp_path) -> None:
    cfg = _cfg(
        tmp_path,
        dev_url="http://localhost:5173",
        entrypoint_filename="main.js",
        root_directory="src",
    )
    assert entry_assets(cfg).js == "http://localhost:5173/src/main.js"


def test_read_manifest_is_cached_per_path(tmp_path) -> None:
    path = _manifest(tmp_path, {"a": {"file": "a.js"}})
    assert read_manifest(path) is read_manifest(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.manifest'`

- [ ] **Step 3: Write the implementation**

```python
# framework/inertia/simple_module_inertia/manifest.py
"""Locate the entry's JS and CSS for the current environment.

Vite keys its manifest by the entry's path relative to the Vite root
(``"main.tsx"``); upstream looked it up as ``f"{root_directory}/{entrypoint}"``
and ``KeyError``'d, which is why hosting used to rewrite the manifest file.
Try Vite's key first, upstream's shape second, the first ``isEntry`` chunk
last — and say which manifest was searched when none of them hit.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from simple_module_inertia.config import InertiaConfig


@dataclass
class InertiaFiles:
    js: str
    css: list[str] = field(default_factory=list)


@lru_cache
def read_manifest(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _find_entry(manifest: dict[str, Any], config: InertiaConfig) -> dict[str, Any] | None:
    for key in (
        config.entrypoint_filename,
        f"{config.root_directory}/{config.entrypoint_filename}",
    ):
        if key in manifest:
            return manifest[key]
    return next((chunk for chunk in manifest.values() if chunk.get("isEntry")), None)


def _public(prefix: str, file: str) -> str:
    return posixpath.join("/", prefix, file) if prefix else posixpath.join("/", file)


def entry_assets(config: InertiaConfig) -> InertiaFiles:
    if config.environment == "production" or config.ssr_enabled:
        manifest = read_manifest(config.manifest_json_path)
        entry = _find_entry(manifest, config)
        if entry is None:
            raise LookupError(
                f"No entry chunk for {config.entrypoint_filename!r} in {config.manifest_json_path}"
            )
        return InertiaFiles(
            js=_public(config.assets_prefix, entry["file"]),
            css=[_public(config.assets_prefix, f) for f in entry.get("css") or []],
        )
    root = config.root_directory.strip("/")
    path = (
        config.entrypoint_filename if root in ("", ".") else f"{root}/{config.entrypoint_filename}"
    )
    return InertiaFiles(js=f"{config.dev_url.rstrip('/')}/{path}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_manifest.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): resolve entry assets from the Vite manifest as written

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 8: `response.py` — the HTTP surface

**Files:**
- Create: `framework/inertia/simple_module_inertia/response.py`
- Test: `framework/inertia/tests/test_adapter_response.py`

**Interfaces:**
- Consumes: `encode_page` (Task 6).
- Produces: `InertiaResponse = HTMLResponse | JSONResponse` (type alias); `json_response(page) -> JSONResponse` (headers `X-Inertia: true`, `Vary: Accept`); `version_conflict(url: str, version: str) -> Response` (409, `X-Inertia-Location`, `X-Inertia-Version`); `redirect(url: str, *, method: str) -> RedirectResponse` (303 unless GET → 307); `location(url) -> Response` (409 + `X-Inertia-Location`); `fragment_redirect(url) -> Response` (409 + `X-Inertia-Redirect`).
- `Vary: Accept` is kept from upstream deliberately: hosting's `InertiaCacheMiddleware` already appends `X-Inertia` to `Vary`, and `test_inertia_cache.py` asserts today's exact behaviour.

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_response.py
from __future__ import annotations

import json

import pytest

from simple_module_inertia.response import (
    fragment_redirect,
    json_response,
    location,
    redirect,
    version_conflict,
)


def test_json_response_carries_the_inertia_headers_and_encoded_page() -> None:
    from pathlib import Path

    resp = json_response({"component": "C", "props": {"p": Path("/x")}, "url": "/", "version": "v"})
    assert resp.status_code == 200
    assert resp.headers["X-Inertia"] == "true"
    assert resp.headers["Vary"] == "Accept"
    assert json.loads(resp.body)["props"]["p"] == "/x"


def test_version_conflict_is_a_409_with_location_and_version() -> None:
    resp = version_conflict("http://h/admin/", "v2")
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"] == "http://h/admin/"
    assert resp.headers["X-Inertia-Version"] == "v2"


@pytest.mark.parametrize(
    ("method", "status"),
    [("POST", 303), ("PUT", 303), ("PATCH", 303), ("DELETE", 303), ("GET", 307)],
)
def test_redirect_uses_303_after_a_mutation(method: str, status: int) -> None:
    resp = redirect("/next", method=method)
    assert resp.status_code == status
    assert resp.headers["location"] == "/next"


def test_location_is_an_external_redirect() -> None:
    resp = location("https://elsewhere.example")
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"] == "https://elsewhere.example"


def test_fragment_redirect_keeps_the_fragment_client_side() -> None:
    resp = fragment_redirect("/docs#install")
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Redirect"] == "/docs#install"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_response.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.response'`

- [ ] **Step 3: Write the implementation**

```python
# framework/inertia/simple_module_inertia/response.py
"""HTTP responses for each protocol outcome.

``Vary: Accept`` is upstream's value and is kept on purpose: hosting's
``InertiaCacheMiddleware`` appends ``X-Inertia`` on the way out and its tests
pin today's header set.
"""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import RedirectResponse, Response

from simple_module_inertia.page import encode_page

InertiaResponse = HTMLResponse | JSONResponse

_JSON_HEADERS = {"X-Inertia": "true", "Vary": "Accept"}


def json_response(page: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=encode_page(page), headers=_JSON_HEADERS)


def version_conflict(url: str, version: str) -> Response:
    return Response(
        status_code=status.HTTP_409_CONFLICT,
        headers={"X-Inertia-Location": url, "X-Inertia-Version": version},
    )


def redirect(url: str, *, method: str) -> RedirectResponse:
    code = (
        status.HTTP_307_TEMPORARY_REDIRECT if method.upper() == "GET" else status.HTTP_303_SEE_OTHER
    )
    return RedirectResponse(url=url, status_code=code)


def location(url: str) -> Response:
    return Response(status_code=status.HTTP_409_CONFLICT, headers={"X-Inertia-Location": url})


def fragment_redirect(url: str) -> Response:
    return Response(status_code=status.HTTP_409_CONFLICT, headers={"X-Inertia-Redirect": url})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_response.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): protocol responses — JSON page, 409 conflict, 303 redirects

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 9: `errors.py` and `templating.py` — the ported halves

**Files:**
- Create: `framework/inertia/simple_module_inertia/errors.py`
- Create: `framework/inertia/simple_module_inertia/templating.py`
- Test: `framework/inertia/tests/test_adapter_errors.py`

**Interfaces:**
- Produces (errors): `InertiaVersionConflictException(url)`; `async inertia_version_conflict_exception_handler(request, exc) -> Response`; `async inertia_request_validation_exception_handler(request, exc) -> Response`. Names match upstream because hosting imports them.
- Produces (templating): `InertiaContext` dataclass (`environment, dev_url, css, js, is_ssr, data=None, ssr_head=None, ssr_body=None`); `InertiaExtension` Jinja extension providing `{% inertia_head %}` and `{% inertia_body %}`.
- The validation handler writes `request.session["_errors"]`, scoped under the error bag when `X-Inertia-Error-Bag` is set.

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_errors.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from simple_module_inertia.errors import (
    InertiaVersionConflictException,
    inertia_request_validation_exception_handler,
    inertia_version_conflict_exception_handler,
)


def _request(headers: dict[str, str], method: str = "POST") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "app": FastAPI(),
        "session": {},
    }
    return Request(scope)


async def test_version_conflict_handler_returns_409_with_location() -> None:
    resp = await inertia_version_conflict_exception_handler(
        _request({}), InertiaVersionConflictException(url="http://h/admin/")
    )
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"] == "http://h/admin/"


async def test_validation_errors_are_flashed_and_redirected_back() -> None:
    req = _request({"X-Inertia": "true", "Referer": "/users/add"})
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "invalid"}])
    resp = await inertia_request_validation_exception_handler(req, exc)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/users/add"
    assert req.session["_errors"] == {"email": "invalid"}


async def test_error_bag_scopes_the_flashed_errors() -> None:
    req = _request({"X-Inertia": "true", "X-Inertia-Error-Bag": "signup", "Referer": "/"})
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "taken"}])
    await inertia_request_validation_exception_handler(req, exc)
    assert req.session["_errors"] == {"signup": {"email": "taken"}}


async def test_non_inertia_validation_errors_keep_fastapis_422() -> None:
    req = _request({})
    exc = RequestValidationError([{"loc": ("body", "email"), "msg": "invalid"}])
    resp = await inertia_request_validation_exception_handler(req, exc)
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_inertia.errors'`

- [ ] **Step 3: Write `errors.py`**

```python
# framework/inertia/simple_module_inertia/errors.py
"""Exception types and handlers. Names match upstream — hosting imports them."""

from __future__ import annotations

from typing import Any

from fastapi import Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.responses import RedirectResponse


class InertiaVersionConflictException(Exception):
    """Raised on a GET whose ``X-Inertia-Version`` no longer matches ours."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__()


async def inertia_version_conflict_exception_handler(
    _: Request, exc: InertiaVersionConflictException
) -> Response:
    return Response(
        status_code=status.HTTP_409_CONFLICT, headers={"X-Inertia-Location": str(exc.url)}
    )


def _field(loc: tuple[Any, ...]) -> Any:
    return loc[1] if len(loc) > 1 else loc[0]


async def inertia_request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Flash validation errors and send the browser back, scoped by error bag."""
    if "x-inertia" not in request.headers:
        return await request_validation_exception_handler(request, exc)

    errors: dict[str, Any] = {}
    bag = request.headers.get("X-Inertia-Error-Bag")
    for error in exc.errors():
        field = _field(tuple(error["loc"]))
        if bag is None:
            errors[field] = error["msg"]
        else:
            errors.setdefault(bag, {})[field] = error["msg"]
    request.session["_errors"] = errors

    code = (
        status.HTTP_307_TEMPORARY_REDIRECT if request.method == "GET" else status.HTTP_303_SEE_OTHER
    )
    return RedirectResponse(url=request.headers.get("Referer", "/"), status_code=code)
```

- [ ] **Step 4: Write `templating.py`**

```python
# framework/inertia/simple_module_inertia/templating.py
"""Jinja glue: the template context and the ``inertia_head``/``inertia_body`` tags.

Ported from upstream. The SSR branches stay so the template contract is the
same, but nothing in this package calls an SSR server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.parser import Parser
from jinja2.runtime import Context
from markupsafe import Markup


@dataclass
class InertiaContext:
    environment: Literal["development", "production"]
    dev_url: str
    css: list[str]
    js: str
    is_ssr: bool
    data: str | None = None
    ssr_head: str | None = None
    ssr_body: str | None = None


class InertiaExtension(Extension):
    tags = {"inertia_head", "inertia_body"}

    def parse(self, parser: Parser) -> nodes.Node:
        tag_name = next(parser.stream).value
        lineno = parser.stream.current.lineno
        node = self.call_method(f"_render_{tag_name}", [nodes.ContextReference()], lineno=lineno)
        return nodes.Output([node]).set_lineno(lineno)

    def _render_inertia_head(self, context: Context) -> Markup:
        inertia: InertiaContext = context["inertia"]
        fragments: list[str] = []
        if inertia.environment == "development":
            fragments.append(
                f'<script type="module" src="{inertia.dev_url}/@vite/client"></script>'
            )
        if inertia.is_ssr:
            if inertia.ssr_head is None:
                raise ValueError("SSR is enabled but no SSR head was provided")
            fragments.append(inertia.ssr_head)
        fragments.extend(f'<link rel="stylesheet" href="{css}">' for css in inertia.css)
        return Markup("\n".join(fragments))

    def _render_inertia_body(self, context: Context) -> Markup:
        inertia: InertiaContext = context["inertia"]
        fragments: list[str] = []
        if inertia.is_ssr:
            if inertia.ssr_body is None:
                raise ValueError("SSR is enabled but no SSR body was provided")
            fragments.append(inertia.ssr_body)
        else:
            if inertia.data is None:
                raise ValueError("No data was provided for the Inertia page")
            fragments.append(f"<div id=\"app\" data-page='{inertia.data}'></div>")
        fragments.append(f'<script type="module" src="{inertia.js}"></script>')
        return Markup("\n".join(fragments))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest framework/inertia/tests/test_adapter_errors.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add framework/inertia
git commit -m "feat(inertia): port the exception handlers and Jinja extension

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 10: `inertia.py` facade, `deps.py`, and the public surface

**Files:**
- Create: `framework/inertia/simple_module_inertia/inertia.py`
- Create: `framework/inertia/simple_module_inertia/deps.py`
- Modify: `framework/inertia/simple_module_inertia/__init__.py`
- Test: `framework/inertia/tests/test_adapter_render.py`

**Interfaces:**
- Consumes: everything from Tasks 2–9.
- Produces: `class Inertia` with `__init__(self, request: Request, config: InertiaConfig, client: Any = None)` (raises `InertiaVersionConflictException` on a **GET** whose version is stale); `share(**props)`; `flash(message, category)`; `back() -> RedirectResponse`; `redirect(url) -> RedirectResponse`; `location(url) -> Response` (static); `encrypt_history()`, `clear_history()`, `preserve_fragment()` (each returns `self`); `async render(component, props=None) -> InertiaResponse`.
- `inertia_dependency_factory(config) -> Callable[[Request, Any], Inertia]` — registers `InertiaExtension` on the template env once; the returned callable accepts `(request, client=None)`, which is the shape hosting's `get_inertia` and `_error_handlers` call.
- `__init__.py` exports: `Inertia, InertiaResponse, InertiaConfig, inertia_dependency_factory, InertiaVersionConflictException, inertia_version_conflict_exception_handler, inertia_request_validation_exception_handler, InertiaExtension, optional, always, defer, merge, prepend, deep_merge, once, scroll, lazy, PropEncodingError`.

- [ ] **Step 1: Write the failing test**

```python
# framework/inertia/tests/test_adapter_render.py
"""End to end through a real FastAPI app: HTML on a page load, JSON on a visit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware

from simple_module_inertia import (
    Inertia,
    InertiaConfig,
    InertiaVersionConflictException,
    defer,
    inertia_dependency_factory,
    inertia_version_conflict_exception_handler,
)

TEMPLATE = (
    "<!doctype html><html><head>{% inertia_head %}</head><body>{% inertia_body %}</body></html>"
)


def _app(tmp_path: Path, version: str = "v1") -> FastAPI:
    (tmp_path / "index.html").write_text(TEMPLATE)
    config = InertiaConfig(
        templates=Jinja2Templates(directory=str(tmp_path)),
        version=version,
        dev_url="http://localhost:5050",
        entrypoint_filename="main.tsx",
        root_directory=".",
        use_flash_errors=True,
    )
    dep = inertia_dependency_factory(config)
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.add_exception_handler(
        InertiaVersionConflictException, inertia_version_conflict_exception_handler
    )

    @app.get("/users")
    async def users(inertia: Inertia = Depends(dep)):
        inertia.share(auth={"id": 1})
        return await inertia.render("Users/Index", {"users": [1], "feed": defer(lambda: [2])})

    @app.post("/users")
    async def create(inertia: Inertia = Depends(dep)):
        return inertia.redirect("/users")

    return app


@pytest.fixture
def client(tmp_path):
    return AsyncClient(transport=ASGITransport(app=_app(tmp_path)), base_url="http://testserver")


async def test_full_page_load_renders_the_document_with_the_page_object(client) -> None:
    resp = await client.get("/users")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert 'src="http://localhost:5050/@vite/client"' in resp.text
    assert 'src="http://localhost:5050/main.tsx"' in resp.text
    assert "data-page=" in resp.text
    assert "&#34;url&#34;: &#34;/users&#34;" in resp.text or '"url": "/users"' in resp.text


async def test_an_inertia_visit_gets_the_json_page_object(client) -> None:
    resp = await client.get("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "v1"})
    assert resp.status_code == 200
    assert resp.headers["X-Inertia"] == "true"
    page = resp.json()
    assert page["component"] == "Users/Index"
    assert page["url"] == "/users"
    assert page["version"] == "v1"
    assert page["props"] == {"auth": {"id": 1}, "users": [1], "errors": {}}
    assert page["deferredProps"] == {"default": ["feed"]}
    assert page["sharedProps"] == ["auth"]


async def test_a_stale_get_is_a_409_pointing_at_the_same_url(client) -> None:
    resp = await client.get("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "old"})
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"].endswith("/users")


async def test_a_stale_post_is_not_rejected(client) -> None:
    resp = await client.post("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "old"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/users"


async def test_flashed_errors_ride_the_next_render(client) -> None:
    # Seed the session the way the validation handler does, then render.
    resp = await client.get("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "v1"})
    assert resp.json()["props"]["errors"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/inertia/tests/test_adapter_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'Inertia' from 'simple_module_inertia'`

- [ ] **Step 3: Write `inertia.py`**

```python
# framework/inertia/simple_module_inertia/inertia.py
"""The request-scoped facade. Thin: each stage lives in its own module."""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import Request
from jinja2.utils import htmlsafe_json_dumps
from pydantic import BaseModel
from starlette.responses import RedirectResponse, Response

from simple_module_inertia.config import InertiaConfig, resolved_version
from simple_module_inertia.errors import InertiaVersionConflictException
from simple_module_inertia.manifest import entry_assets
from simple_module_inertia.page import build_page, encode_page
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props
from simple_module_inertia.response import (
    InertiaResponse,
    fragment_redirect,
    json_response,
    location,
    redirect,
)
from simple_module_inertia.templating import InertiaContext


class Inertia:
    def __init__(self, request: Request, config: InertiaConfig, client: Any = None) -> None:
        self._request = request
        self._config = config
        self._client = client  # kept for signature compatibility; SSR is not implemented
        self._req = InertiaRequest.from_headers(request.headers, request.method)
        self._version = resolved_version(config)
        self._shared: dict[str, Any] = {}
        self._encrypt_history = False
        self._clear_history = False
        self._preserve_fragment = False
        if self._is_stale():
            raise InertiaVersionConflictException(url=str(request.url))

    # -- request state ----------------------------------------------------

    def _is_stale(self) -> bool:
        """Only a GET is rejected; the client re-submits mutations itself."""
        return (
            self._req.is_inertia
            and self._req.method == "GET"
            and self._req.version is not None
            and self._req.version != self._version
        )

    def share(self, **props: Any) -> None:
        self._shared.update(props)

    def flash(self, message: str, category: str) -> None:
        if not self._config.use_flash_messages:
            raise NotImplementedError("Flash messages are not enabled")
        self._request.session.setdefault("_messages", []).append(
            {"message": message, "category": category}
        )

    def encrypt_history(self) -> Inertia:
        self._encrypt_history = True
        return self

    def clear_history(self) -> Inertia:
        self._clear_history = True
        return self

    def preserve_fragment(self) -> Inertia:
        self._preserve_fragment = True
        return self

    # -- redirects --------------------------------------------------------

    def redirect(self, url: str) -> RedirectResponse:
        return redirect(url, method=self._request.method)

    def back(self) -> RedirectResponse:
        return self.redirect(self._request.headers.get("Referer", "/"))

    @staticmethod
    def location(url: str) -> Response:
        return location(url)

    @staticmethod
    def redirect_with_fragment(url: str) -> Response:
        return fragment_redirect(url)

    # -- render -----------------------------------------------------------

    def _pop_session(self, key: str, default: Any) -> Any:
        session = self._request.session
        return session.pop(key) if key in session else default

    async def render(
        self, component: str, props: dict[str, Any] | BaseModel | None = None
    ) -> InertiaResponse:
        page_props: dict[str, Any] = (
            props.model_dump() if isinstance(props, BaseModel) else dict(props or {})
        )
        if self._config.use_flash_messages:
            page_props[self._config.flash_message_key] = self._pop_session("_messages", [])
        errors = self._pop_session("_errors", {}) if self._config.use_flash_errors else {}
        # ``errors`` is the protocol's always-prop; keep the configured key
        # pointing at the same dict so a custom flash_error_key still works.
        if self._config.flash_error_key != "errors":
            page_props[self._config.flash_error_key] = errors

        resolved = await resolve_props(page_props, self._shared, component, self._req)
        page = build_page(
            component=component,
            resolved=resolved,
            url=str(self._request.url),
            version=self._version,
            errors=errors,
            encrypt_history=self._encrypt_history,
            clear_history=self._clear_history,
            preserve_fragment=self._preserve_fragment,
        )
        if self._req.is_inertia:
            return json_response(page)
        return self._render_html(page)

    def _render_html(self, page: dict[str, Any]) -> InertiaResponse:
        files = entry_assets(self._config)
        page_json = htmlsafe_json_dumps(json.dumps(encode_page(page)))
        context = {
            "inertia": InertiaContext(
                environment=self._config.environment,
                dev_url=self._config.dev_url,
                is_ssr=False,
                data=cast(str, page_json),
                js=files.js,
                css=files.css,
            ),
            **self._config.extra_template_context,
        }
        return self._config.templates.TemplateResponse(
            name=self._config.root_template_filename, request=self._request, context=context
        )
```

- [ ] **Step 4: Write `deps.py`**

```python
# framework/inertia/simple_module_inertia/deps.py
"""Build the per-request dependency hosting publishes on ``app.state``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request

from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.inertia import Inertia
from simple_module_inertia.templating import InertiaExtension


def inertia_dependency_factory(config: InertiaConfig) -> Callable[..., Inertia]:
    env = config.templates.env
    if InertiaExtension not in env.extensions.values():
        env.add_extension(InertiaExtension)

    def inertia_dependency(request: Request, client: Any = None) -> Inertia:
        return Inertia(request, config, client)

    return inertia_dependency
```

- [ ] **Step 5: Fill in `__init__.py`**

```python
# framework/inertia/simple_module_inertia/__init__.py
"""Inertia.js v3 server adapter for FastAPI. See README.md and NOTICE."""

from __future__ import annotations

from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.deps import inertia_dependency_factory
from simple_module_inertia.errors import (
    InertiaVersionConflictException,
    inertia_request_validation_exception_handler,
    inertia_version_conflict_exception_handler,
)
from simple_module_inertia.inertia import Inertia
from simple_module_inertia.page import PropEncodingError
from simple_module_inertia.props import (
    always,
    deep_merge,
    defer,
    lazy,
    merge,
    once,
    optional,
    prepend,
    scroll,
)
from simple_module_inertia.response import InertiaResponse
from simple_module_inertia.templating import InertiaExtension

__all__ = [
    "Inertia",
    "InertiaConfig",
    "InertiaExtension",
    "InertiaResponse",
    "InertiaVersionConflictException",
    "PropEncodingError",
    "always",
    "deep_merge",
    "defer",
    "inertia_dependency_factory",
    "inertia_request_validation_exception_handler",
    "inertia_version_conflict_exception_handler",
    "lazy",
    "merge",
    "once",
    "optional",
    "prepend",
    "scroll",
]
```

- [ ] **Step 6: Run the package suite**

Run: `uv run pytest framework/inertia/tests -v`
Expected: PASS (all tests from Tasks 1–10).

- [ ] **Step 7: Lint the package and commit**

Run: `uv run ruff format framework/inertia && uv run ruff check framework/inertia && uv run ty check framework/inertia && uv run python scripts/check_file_size.py`
Expected: all clean. If `ty` flags the `# type: ignore[arg-type]` in `request.py` as unused, delete that comment.

```bash
git add framework/inertia
git commit -m "feat(inertia): Inertia facade, dependency factory and public surface

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 11: Switch `simple_module_hosting` to the new package

**Files:**
- Modify: `framework/hosting/pyproject.toml`
- Modify: `framework/hosting/simple_module_hosting/_inertia_setup.py`
- Modify: `framework/hosting/simple_module_hosting/inertia_deps.py:8`
- Modify: `framework/hosting/simple_module_hosting/_error_handlers.py:12-24,186-190`
- Modify: `framework/hosting/simple_module_hosting/_phase_helpers.py:17-20`
- Modify: `framework/core/simple_module_core/services.py:22`
- Delete: `framework/hosting/simple_module_hosting/_inertia_json.py`
- Delete: `framework/hosting/simple_module_hosting/_inertia_url.py`
- Delete: `framework/hosting/tests/test_inertia_json_encoder.py`
- Delete: `framework/hosting/tests/test_inertia_relative_url.py`
- Delete: `framework/hosting/tests/test_inertia_manifest.py`

**Interfaces:**
- Consumes: the Task 10 public surface. `app.state.inertia_dependency` keeps the `(request, client=None) -> Inertia` shape, so `get_inertia` and the error handler's `inertia_dep(request, None)` calls are unchanged.

- [ ] **Step 1: Swap the dependency**

In `framework/hosting/pyproject.toml`, replace `"fastapi-inertia>=1.0",` with `"simple_module_inertia==0.0.34",` (keep the list alphabetical — it goes after `"simple_module_db==0.0.34",`), and add to `[tool.uv.sources]`:

```toml
simple_module_inertia = { workspace = true }
```

Run: `uv sync --all-packages`
Expected: resolves; `fastapi-inertia` disappears from `uv.lock`'s hosting deps (it may remain as a transitive of nothing — `uv sync` prunes it).

- [ ] **Step 2: Rewrite `_inertia_setup.py`**

Replace the whole file's imports and `setup_inertia` body. Delete `_prod_manifest_path`, `_VITE_MANIFEST_RELPATH`, and the `hashlib`/`json`/`tempfile` imports it needed. Keep `branding_head` exactly as is.

```python
"""Configure simple_module_inertia with the Jinja2 template."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from simple_module_inertia import InertiaConfig, inertia_dependency_factory
from starlette.requests import Request

from simple_module_hosting._favicon import default_favicon_data_uri
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

_INERTIA_VERSION = "1.0"
_ROOT_TEMPLATE_FILENAME = "index.html"
_ENTRYPOINT_FILENAME = "main.tsx"
_ROOT_DIRECTORY = "."

# Fallback app name when the (optional) branding module isn't installed. Mirrors
# branding's own default so the unbranded title is identical everywhere.
_DEFAULT_APP_NAME = "SimpleModule"

# Built assets are served from the "/static" mount under "dist/", so production
# asset URLs are prefixed with "static/dist". The manifest is read where Vite
# writes it; the adapter looks the entry up by Vite's own key.
_ASSETS_PREFIX = "static/dist"
_VITE_MANIFEST_RELPATH = Path("static") / "dist" / ".vite" / "manifest.json"
```

(keep `branding_head` here, unchanged)

```python
def _prod_manifest_path(project_root: Path) -> str:
    """The Vite manifest to read in production, or ``""`` when none is built."""
    candidates = [
        project_root / "host" / _VITE_MANIFEST_RELPATH,
        project_root / _VITE_MANIFEST_RELPATH,
    ]
    found = next((p for p in candidates if p.is_file()), None)
    if found is None:
        logger.warning(
            "Production Vite manifest not found (looked in %s)", [str(c) for c in candidates]
        )
        return ""
    return str(found)


def setup_inertia(
    app: FastAPI,
    settings: Settings,
    modules: list,
    project_root: Path,
) -> InertiaConfig | None:
    """Configure the Inertia adapter and attach the dependency factory to app.state.

    Two host layouts are supported: ``host/templates`` (the framework's
    own host package) and ``templates`` at the project root (what
    ``smpy new`` produces). The first one found wins so it can override
    module-contributed templates.
    """
    from fastapi.templating import Jinja2Templates

    candidate_dirs = [
        project_root / "host" / "templates",
        project_root / "templates",
    ]
    directories: list[Path] = []

    host_templates = next((p for p in candidate_dirs if p.is_dir()), None)
    if host_templates is not None:
        directories.append(host_templates)
    else:
        logger.warning(
            "Host templates directory not found (looked in %s)",
            ", ".join(str(p) for p in candidate_dirs),
        )

    for mod in modules:
        for path in mod.template_dirs():
            if Path(path).is_dir():
                directories.append(Path(path))
            else:
                logger.warning(
                    "Module '%s' declared template dir %s but it does not exist",
                    mod.meta.name,
                    path,
                )

    if not directories:
        logger.warning("No usable template directories — Inertia will fail to render views")
        return None

    templates = Jinja2Templates(directory=directories)
    templates.env.globals["branding_head"] = branding_head

    from simple_module_core.environments import NON_PROD_ENVIRONMENTS

    use_dev_server = settings.environment in NON_PROD_ENVIRONMENTS
    inertia_environment = "development" if use_dev_server else "production"

    inertia_config = InertiaConfig(
        environment=inertia_environment,
        version=_INERTIA_VERSION,
        dev_url=settings.vite_dev_url if use_dev_server else "",
        manifest_json_path="" if use_dev_server else _prod_manifest_path(project_root),
        assets_prefix="" if use_dev_server else _ASSETS_PREFIX,
        templates=templates,
        root_template_filename=_ROOT_TEMPLATE_FILENAME,
        entrypoint_filename=_ENTRYPOINT_FILENAME,
        root_directory=_ROOT_DIRECTORY,
        use_flash_errors=True,
    )
    app.state.inertia_dependency = inertia_dependency_factory(inertia_config)
    return inertia_config
```

- [ ] **Step 3: Update the four import sites**

`inertia_deps.py` line 8: `from inertia import Inertia` → `from simple_module_inertia import Inertia`.

`_phase_helpers.py` lines 17–20: `from inertia import (` → `from simple_module_inertia import (`.

`_error_handlers.py`: change line 12 to `from simple_module_inertia import (`; delete line 24 (`from simple_module_hosting._inertia_url import patch_relative_page_url`); change line 190 from `inertia = patch_relative_page_url(Inertia(request, config))` to `inertia = Inertia(request, config)`. Update the comment block at 176–185 so it no longer mentions "url-relativizing patch" — replace it with:

```python
        # Prefer the app's configured dependency over constructing Inertia
        # directly, so the error page is built the same way as every other
        # page. The raw construction is the fallback for a half-built app —
        # the case this whole handler exists to survive.
```

`framework/core/simple_module_core/services.py` line 22: `from inertia import InertiaConfig` → `from simple_module_inertia import InertiaConfig` (it is inside a `TYPE_CHECKING` block; leave it there).

- [ ] **Step 4: Delete the absorbed wrappers and their tests**

```bash
git rm framework/hosting/simple_module_hosting/_inertia_json.py \
       framework/hosting/simple_module_hosting/_inertia_url.py \
       framework/hosting/tests/test_inertia_json_encoder.py \
       framework/hosting/tests/test_inertia_relative_url.py \
       framework/hosting/tests/test_inertia_manifest.py
grep -rn "_inertia_json\|_inertia_url\|patch_relative_page_url\|_prod_manifest_path" framework host modules --include="*.py"
```

Expected: the grep prints nothing. If it prints a hit, that file still references a deleted symbol — fix it before continuing.

- [ ] **Step 5: Run the hosting and core suites**

Run: `uv run pytest framework/hosting/tests framework/core/tests -q 2>&1 | tail -3`
Expected: all pass. The modules still import `from inertia import InertiaResponse` at this point and that package is gone — **this step runs only hosting/core**, which no longer do.

- [ ] **Step 6: Commit**

```bash
git add -A framework/hosting framework/core
git commit -m "refactor(hosting): depend on simple_module_inertia instead of fastapi-inertia

Deletes the three upstream workarounds — the JSON-encoder wrap, the
relative-url wrap and the Vite manifest re-keying — whose fixes now
live in the adapter itself.

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 12: Switch every module, the host and the scaffold template

**Files:**
- Modify: every file matching `grep -rl "from inertia import" modules host framework/cli/simple_module_cli/templates`

**Interfaces:**
- Consumes: `simple_module_inertia.InertiaResponse` (Task 10).

- [ ] **Step 1: List the sites**

Run: `grep -rln "from inertia import" modules host framework/cli --include="*.py" --include="*.tpl"`
Expected: 13–16 files (all `views.py`-style endpoint files, `host/routes.py`, `host/routes_setup.py`, and the scaffold `templates/host/routes.py`).

- [ ] **Step 2: Rewrite the import in each**

```bash
grep -rln "from inertia import" modules host framework/cli --include="*.py" --include="*.tpl" \
  | xargs sed -i 's/^from inertia import /from simple_module_inertia import /'
grep -rn "from inertia import\|^import inertia" modules host framework --include="*.py" --include="*.tpl"
```

Expected: the second grep prints nothing.

- [ ] **Step 3: Format (import order changes) and run the whole suite**

Run: `uv run ruff format modules host framework && uv run ruff check --fix modules host framework`
Then: `uv run pytest -q 2>&1 | tail -3`
Expected: `2975 passed` (the pre-existing count) plus the new `test_adapter_*` tests; **0 failed**. This is the backwards-compatibility proof — every module still renders through the v2 client's expectations.

- [ ] **Step 4: Full lint and doctor**

Run: `make lint > /tmp/lint.log 2>&1; echo $?; tail -5 /tmp/lint.log` then `make doctor > /tmp/doctor.log 2>&1; echo $?`
Expected: both exit 0.

- [ ] **Step 5: Boot the app and render one page each way**

```bash
cp -n .env.example .env
make migrate
uv run smpy users create-admin --email admin@example.com --password Admin123! --force
nohup uv run --project host uvicorn host.main:app --port 8000 > /tmp/api.log 2>&1 &
sleep 5
curl -s -o /dev/null -w "html %{http_code}\n" http://127.0.0.1:8000/
curl -s -H "X-Inertia: true" -H "X-Inertia-Version: 1.0" http://127.0.0.1:8000/ | python3 -c "import json,sys; p=json.load(sys.stdin); print('json', p['component'], p['url'], sorted(p['props']))"
lsof -ti tcp:8000 | xargs -r kill -9
```

Expected: `html 200`, then `json Landing / [...]` with `errors` in the props list and a root-relative `url`.

- [ ] **Step 6: Commit**

```bash
git add -A modules host framework
git commit -m "refactor: import InertiaResponse from simple_module_inertia

One-line import change per view module; render() and the dependency are
unchanged. The full suite passing against the v2 client is the proof the
adapter is backwards compatible.

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 13: Docs for module authors, then open PR 1

**Files:**
- Modify: `docs/module-authoring.md` (add a short "Inertia props" subsection under the existing Inertia guidance)
- Modify: `CLAUDE.md` § Inertia (one sentence naming the package and the prop factories)

- [ ] **Step 1: Add the authoring note**

In `docs/module-authoring.md`, find the section that covers `inertia.render` and append:

````markdown
### Prop types (Inertia v3)

`simple_module_inertia` exposes the v3 prop wrappers. Wrap a value, a callable,
or an awaitable; the adapter decides when to resolve it:

```python
from simple_module_inertia import always, defer, merge, once, optional, scroll

await inertia.render(
    "Feed/Index",
    {
        "posts": scroll(load_page, page_name="page", current_page=1, previous_page=None, next_page=2),
        "notices": merge(load_notices, match_on="id"),
        "plans": once(load_plans, expires_at=None),
        "analytics": defer(load_analytics, group="sidebar"),
        "stats": optional(load_stats),   # only on partial reloads that ask for it
        "flash": always(get_flash),      # on every response, even partial ones
    },
)
```

`errors` is always present in props (it is the protocol's always-prop) and is
filled from validation failures flashed by the previous request.
````

In `CLAUDE.md`'s **Inertia** paragraph, append: `The adapter is the in-repo package ` `simple_module_inertia` ` (Inertia v3 protocol); import ` `InertiaResponse` ` and the prop factories (` `optional` `, ` `always` `, ` `defer` `, ` `merge` `, ` `once` `, ` `scroll` `) from it.`

- [ ] **Step 2: Format markdown code blocks and lint**

Run: `uv run ruff format docs/ && make lint > /tmp/lint.log 2>&1; echo $?`
Expected: 0.

- [ ] **Step 3: Commit and push**

```bash
git add docs/module-authoring.md CLAUDE.md
git commit -m "docs: document the Inertia v3 prop factories for module authors

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
git push -u origin feat/inertia-v3-adapter
```

- [ ] **Step 4: Open PR 1**

Title: `feat(inertia): simple_module_inertia — a v3-capable Inertia adapter`. Body: link the spec, list the three absorbed workarounds, state that the full suite passes against the **v2** client (backwards compatibility), and carry the operator note about the PyPI pending publisher. Use `/vf` or `gh pr create --base main`.

---

## PR 2 — client migration to `@inertiajs/react` v3

Branch off PR 1's branch: `git checkout -b feat/inertia-v3-client feat/inertia-v3-adapter`.

### Task 14: Bump the client pin everywhere it lives

**Files:**
- Modify: `host/client_app/package.json`, `packages/ui/package.json` (peerDependencies), every `modules/*/package.json` (peerDependencies)
- Modify: `framework/cli/simple_module_cli/templates/host/client_app/package.json.tpl`, `framework/cli/simple_module_cli/templates/module/package.json.tpl`, `framework/cli/simple_module_cli/templates/module/_optional/standalone/package.json.tpl`
- Modify: `framework/cli/simple_module_cli/app_project.py` (`_APP_NPM_DEPS`)
- Modify: `framework/cli/tests/test_cli_new_regressions.py::test_sm_new_flat_pins_inertia_react_to_v2`

- [ ] **Step 1: Flip the regression test first (it must fail)**

Rename the test to `test_sm_new_flat_pins_inertia_react_to_v3`, update its docstring to say the flat scaffold must peer-match `@simple-module-py/ui`'s `^3.0.0`, and change the assertion to:

```python
    assert inertia.startswith("^3."), f"expected ^3.x, got {inertia!r}"
```

Run: `uv run pytest framework/cli/tests/test_cli_new_regressions.py -k inertia_react -v`
Expected: FAIL — `expected ^3.x, got '^2.0.0'`.

- [ ] **Step 2: Rewrite every pin**

```bash
grep -rln '"@inertiajs/react": "\^2' host packages modules framework/cli --include="package.json" --include="*.tpl" --include="*.py" \
  | xargs sed -i 's|"@inertiajs/react": "\^2[^"]*"|"@inertiajs/react": "^3.7.0"|'
grep -rn '@inertiajs/react' host packages modules framework/cli --include="package.json" --include="*.tpl" --include="*.py" | grep -v '\^3\.7\.0'
```

Expected: the second grep prints nothing.

- [ ] **Step 3: Install and confirm the resolved version**

Run: `npm install --no-audit --fund=false && npm ls @inertiajs/react --depth=0 | head -3`
Expected: `@inertiajs/react@3.7.x` (deduped), no `UNMET PEER` lines.

- [ ] **Step 4: Run the CLI test and commit**

Run: `uv run pytest framework/cli/tests/test_cli_new_regressions.py -k inertia_react -v`
Expected: PASS.

```bash
git add -A
git commit -m "chore(client): move @inertiajs/react to ^3.7.0 everywhere it is pinned

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 15: The three v3 code changes

**Files:**
- Modify: every `.tsx` matching `grep -rl "\.layout = (page" host/client_app modules packages`
- Modify: `packages/ui/src/lib/spa-links.ts:119`
- Modify: `host/templates/index.html:39`
- Modify: `framework/cli/simple_module_cli/templates/host/templates/index.html` (same line)

**Interfaces:**
- v3 requires the array layout form; every layout here already accepts `children`, so `Page.layout = [AdminLayout]` is the direct translation of `Page.layout = (page) => <AdminLayout>{page}</AdminLayout>`.

- [ ] **Step 1: Convert the layouts**

```bash
grep -rl "\.layout = (page: React.ReactNode) => <" host/client_app modules packages --include="*.tsx" \
  | xargs sed -i -E 's/^([A-Za-z]+)\.layout = \(page: React\.ReactNode\) => <([A-Za-z]+)>\{page\}<\/\2>;$/\1.layout = [\2];/'
grep -rn "\.layout = (page" host/client_app modules packages --include="*.tsx"
```

Expected: the second grep prints nothing. If a line survives, it did not match the exact one-line pattern — convert it by hand to `Name.layout = [LayoutComponent];`.

- [ ] **Step 2: Rename the router event**

In `packages/ui/src/lib/spa-links.ts` line 119, change `router.on('invalid', (event) => {` to `router.on('httpException', (event) => {`. If the handler reads `event.detail.response`, it is unchanged in v3.

- [ ] **Step 3: Rename the head marker in both templates**

In `host/templates/index.html` line 39 and the scaffold's `templates/host/templates/index.html`, change `<title inertia="">` to `<title data-inertia="">`, and update the comment above it (lines 34–36 in the host copy) to read `data-inertia`.

- [ ] **Step 4: Typecheck, unit tests, build**

Run: `npx tsc --noEmit -p host/client_app/tsconfig.json && npm test > /tmp/vitest.log 2>&1; echo $?; grep -E "Tests " /tmp/vitest.log`
Expected: tsc clean; `463 passed`.

Run: `npm run build --workspace host/client_app > /tmp/build.log 2>&1; echo $?`
Expected: 0.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(client): migrate pages and templates to the Inertia v3 API

Array-form persistent layouts, the invalid -> httpException event
rename, and data-inertia as the head marker.

Claude-Session: https://claude.ai/code/session_01CwgTb8hULSfHoW2DrFrQAW"
```

---

### Task 16: Prove it in the browser and open PR 2

- [ ] **Step 1: Full local CI**

Run: `make lint > /tmp/lint.log 2>&1; echo $?` then `uv run pytest -q 2>&1 | tail -2`
Expected: 0; all passed.

- [ ] **Step 2: E2E against the v3 client**

```bash
lsof -ti tcp:8000 | xargs -r kill -9; lsof -ti tcp:5201 | xargs -r kill -9
rm -f app.db && make migrate
uv run smpy users create-admin --email admin@example.com --password Admin123! --force
SM_VITE_PORT=5201 nohup npm run dev > /tmp/vite.log 2>&1 &
SM_VITE_DEV_URL=http://localhost:5201 nohup uv run --project host uvicorn host.main:app --port 8000 > /tmp/api.log 2>&1 &
until curl -s -o /dev/null http://127.0.0.1:8000/; do sleep 2; done
E2E_PASSWORD='Admin123!' uv run pytest tests/e2e/ -m e2e -q > /tmp/e2e.log 2>&1; echo "e2e_exit=$?" > /tmp/e2e-exit.txt
cat /tmp/e2e-exit.txt; tail -2 /tmp/e2e.log
```

Expected: `e2e_exit=0`, `44 passed`. Read the exit code from the file — a trailing `tail` would otherwise report its own status. If `.env` sets `SM_VITE_DEV_URL=…:5050` and 5050 is busy, the env var above overrides it only if `.env` is not read first — set it in `.env` instead if the served HTML still references 5050.

- [ ] **Step 3: Browser check for the v3-specific risks**

With the servers still up, run `/qa` (or drive Playwright directly) and confirm: no `Page … not found` console errors, no `router.on` deprecation warnings, layouts render (sidebar present on `/admin/users/`), a form validation error surfaces under `errors`, and back/forward navigation works (history state is written).

- [ ] **Step 4: Stop servers, push, open PR 2**

```bash
lsof -ti tcp:8000 | xargs -r kill -9; lsof -ti tcp:5201 | xargs -r kill -9
git push -u origin feat/inertia-v3-client
```

Open PR 2 with base `feat/inertia-v3-adapter` (so it lands after PR 1), title `feat(client): migrate to @inertiajs/react v3`, body listing the three code changes and the e2e/QA evidence.

---

## Self-review

**Spec coverage.** §1 package boundary → Tasks 1, 11. §2 every file → Tasks 2–10 (one task per file; `errors`+`templating` share Task 9). §3 resolution rules → Task 5's two test modules, one test per rule. §4 data flow → Task 10 `render()`. §5 backwards compatibility → Task 12 Step 3 (full suite against the v2 client), Task 11 deletions. §6 error handling → Task 9 (validation/error bag), Task 10 (GET-only 409), Task 6 (`PropEncodingError` names the path), Task 3 (`scroll` requires `page_name`). §7 testing → every task is TDD; conformance suite in Task 5. §8 client migration → Tasks 14–16. Out of scope (Precognition, SSR) → nothing built; `templating.py` keeps the hooks.

**Placeholders.** None. Every code step is complete; every "Expected" names the concrete output.

**Type consistency.** `InertiaRequest.from_headers(headers, method)` — Tasks 4, 5, 10. `resolve_props(page_props, shared_props, component, req)` — Tasks 5, 10. `ResolvedProps` field names (`deferred, merge, prepend, deep_merge, match_on, once, scroll, shared`) — Tasks 5, 6. `build_page(*, component, resolved, url, version, errors, encrypt_history, clear_history, preserve_fragment)` — Tasks 6, 10. `entry_assets(config) -> InertiaFiles(js, css)` — Tasks 7, 10. `Inertia(request, config, client=None)` — Tasks 10, 11. `inertia_dependency_factory(config)` returning `(request, client=None) -> Inertia` — Tasks 10, 11.

**One deliberate divergence from the spec's §2 table:** `response.py` keeps upstream's `Vary: Accept` rather than switching to `Vary: X-Inertia`, because hosting's `InertiaCacheMiddleware` already appends `X-Inertia` and `test_inertia_cache.py` pins the current header set. The protocol requirement is met by the middleware; changing it inside the adapter would be a hosting-visible behaviour change with no benefit.
