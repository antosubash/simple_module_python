"""Emit generated-resources.ts + keys.generated.ts for the frontend.

Both files are consumed by ``@simple-module-py/i18n``:

* ``generated-resources.ts`` — flat empty-string keys, fed into i18next's
  ``CustomTypeOptions['resources']`` so ``t('foo.bar')`` narrows to the
  accepted key union.

* ``keys.generated.ts`` — a nested ``keys`` constant whose leaves are the
  full dotted key strings. Consumers use ``t(keys.foo.bar)`` for typed
  call-sites.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from simple_module_core import ModuleBase
from simple_module_core.localization.i18n import PLURAL_CATEGORIES, I18nRegistry

from simple_module_hosting._i18n_build import build_i18n_registry
from simple_module_hosting._i18n_target import (
    app_i18n_dir,
    attach_app_i18n,
    read_resource_keys,
    resolve_i18n_types_dir,
)
from simple_module_hosting.manifest import _write_if_changed
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)


def emit_frontend_types_for_modules(
    settings: Settings,
    installed_modules: list[ModuleBase],
    project_root: Path,
    *,
    strict: bool = False,
    allow_removals: bool = False,
) -> None:
    """Emit the TS key union covering every *installed* module.

    Deliberately not the booted module list. ``make lint`` runs
    ``tsc -p modules/<name>`` for each module in the workspace, including the
    auth provider this host did not activate; those pages still call
    ``t(keys.<namespace>…)``, so their keys must be in the union even though
    the module is inert here. The runtime registry stays filtered — an
    inactive module's strings are typed, never served.
    """
    registry, _ = build_i18n_registry(settings, installed_modules, project_root)
    emit_frontend_types(registry, project_root, strict=strict, allow_removals=allow_removals)
    from simple_module_hosting._i18n_modules import emit_module_keys

    emit_module_keys(installed_modules, settings, strict=strict)


def emit_frontend_types(
    registry: I18nRegistry,
    project_root: Path,
    *,
    strict: bool = False,
    allow_removals: bool = False,
) -> None:
    """Write an app-owned aggregate, plus monorepo compatibility exports.

    Strict generation raises on errors and accidental namespace removal. The
    development boot logs failures so stale types cannot break the running app.
    Installed npm packages are never rewritten.
    """
    pkg_src, published = resolve_i18n_types_dir(project_root)
    if pkg_src is None:
        if strict:
            raise FileNotFoundError(
                f"no @simple-module-py/i18n found for {project_root} (packages/i18n/src or "
                "node_modules/@simple-module-py/i18n/src) — run `npm install` first"
            )
        return
    resources_path = pkg_src / "generated-resources.ts"
    if not allow_removals:
        dropped = find_dropped_namespaces(
            resources_path, registry.messages(registry.default_locale)
        )
        if dropped:
            error = NamespaceRemovalError(dropped)
            if strict:
                raise error
            logger.warning("%s Not writing the generated i18n files.", error)
            return
    try:
        write_generated_resources(registry, pkg_src, augment=published)
        app_target = app_i18n_dir(project_root)
        if app_target is not None and app_target != pkg_src:
            write_generated_resources(registry, app_target, augment=True)
        if app_target is not None:
            attach_app_i18n(app_target.parent)
    except Exception:
        if strict:
            raise
        logger.exception("Failed to write generated-resources.ts — frontend types will be stale")


class NamespaceRemovalError(RuntimeError):
    """Regenerating would delete whole key namespaces from the checked-in files."""

    def __init__(self, dropped: dict[str, int]) -> None:
        self.dropped = dropped
        detail = ", ".join(f"'{ns}.*' ({n} keys)" for ns, n in sorted(dropped.items()))
        super().__init__(
            f"regenerating would drop {detail} — the module(s) are not installed in "
            "this environment. Run `uv sync --all-packages` first, or pass "
            "--allow-removals (`make gen-i18n ARGS=--allow-removals`) if the module was "
            "genuinely deleted."
        )


def find_dropped_namespaces(resources_path: Path, new_messages: Any) -> dict[str, int]:
    """Top-level namespaces in the existing resources file absent from ``new_messages``.

    Returns ``{namespace: existing key count}``. Empty when the file is absent
    or unreadable (nothing to lose).
    """
    old = Counter(key.split(".", 1)[0] for key in read_resource_keys(resources_path))
    new = {key.split(".", 1)[0] for key in new_messages}
    return {ns: n for ns, n in old.items() if ns not in new}


_RESOURCES_HEADER = (
    "// AUTO-GENERATED by simple_module_hosting.i18n_manifest — do not edit by hand.\n"
    "// Regenerate by booting the host in development mode or `make gen-i18n`."
)

_KEYS_HEADER = _RESOURCES_HEADER

_PLURAL_SUFFIXES: tuple[str, ...] = tuple(f"_{c}" for c in PLURAL_CATEGORIES)


def write_generated_resources(
    registry: I18nRegistry,
    output_dir: Path,
    *,
    extra_keys: Iterable[str] = (),
    augment: bool = False,
) -> Path:
    """Write both ``generated-resources.ts`` and ``keys.generated.ts``.

    Returns the path of the resources file. Both files skip the disk write
    when content matches what's already on disk (to avoid bumping mtimes
    that would trigger spurious Vite HMR). ``extra_keys`` are unioned into the
    registry's keys for callers retaining an additional compatibility catalog.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    messages = registry.messages(registry.default_locale)
    keys = sorted({*messages.keys(), *extra_keys})

    resources_path = output_dir / "generated-resources.ts"
    resources = _render_resources(keys)
    if augment:
        resources = resources.replace("export default {", "const resources = {")
        resources += (
            "\nexport default resources;\n"
            "type AppTranslationResources = typeof resources.translation;\n"
            "declare module '@simple-module-py/i18n' {\n"
            "  interface TranslationResources extends AppTranslationResources {}\n}\n"
        )
        resources = (
            "// biome-ignore-all lint/style/useConsistentTypeDefinitions: generated augmentation.\n"
            "import '@simple-module-py/i18n';\n\n" + resources
        )
    if _write_if_changed(resources_path, resources):
        logger.info("Wrote %s (%d keys)", resources_path.name, len(keys))

    keys_path = output_dir / "keys.generated.ts"
    rendered_keys = _render_keys(keys)
    if augment:
        rendered_keys = (
            "import { registerTranslationKeys } from '@simple-module-py/i18n';\n"
            "import './generated-resources';\n\n"
            + rendered_keys
            + "\ntype AppTranslationKeys = typeof keys;\n"
            "declare module '@simple-module-py/i18n' {\n"
            "  interface TranslationKeys extends AppTranslationKeys {}\n}\n"
            "registerTranslationKeys(keys);\n"
        )
    if _write_if_changed(keys_path, rendered_keys):
        logger.info("Wrote %s", keys_path.name)

    return resources_path


def _render_resources(keys: list[str]) -> str:
    lines = [_RESOURCES_HEADER, "export default {", "  translation: {"]
    for key in keys:
        lines.append(f"    '{key}': '',")
    lines.append("  },")
    lines.append("} as const;")
    lines.append("")
    return "\n".join(lines)


def _render_keys(keys: list[str]) -> str:
    """Render the nested ``keys`` constant tree."""
    tree = _build_key_tree(keys)
    return f"{_KEYS_HEADER}\n\nexport const keys = {_serialize(tree, indent=0)} as const;\n"


def _build_key_tree(flat_keys: list[str]) -> dict[str, Any]:
    """Build a nested dict from a list of dotted keys.

    Leaves are the full dotted key string. Plural stems (e.g. ``foo.items``
    when ``foo.items_one``/``foo.items_other`` exist) are added as virtual
    leaves so callers can pass them directly to ``t(key, {count})``.
    """
    tree: dict[str, Any] = {}
    stems: set[str] = set()

    for flat_key in flat_keys:
        for suffix in _PLURAL_SUFFIXES:
            if flat_key.endswith(suffix):
                stems.add(flat_key[: -len(suffix)])
                break
        _insert(tree, flat_key.split("."), flat_key)

    existing = set(flat_keys)
    for stem in stems:
        if stem in existing:
            continue
        _insert(tree, stem.split("."), stem)

    return tree


def _insert(tree: dict[str, Any], path: list[str], value: str) -> None:
    """Insert ``value`` into ``tree`` at ``path``.

    Existing leaves win over later inserts — real keys cannot be shadowed
    by virtual plural stems, and a path segment that collides with an
    existing leaf causes the insertion to be silently aborted.
    """
    cursor: Any = tree
    for segment in path[:-1]:
        existing = cursor.get(segment)
        if isinstance(existing, dict):
            cursor = existing
        elif existing is None:
            new_dict: dict[str, Any] = {}
            cursor[segment] = new_dict
            cursor = new_dict
        else:
            return
    leaf_key = path[-1]
    if leaf_key not in cursor:
        cursor[leaf_key] = value


def _serialize(node: Any, *, indent: int) -> str:
    """Emit a dict-of-dicts tree as pretty-printed TypeScript object literal.

    Strings are wrapped in single quotes to match the project's biome config
    (``quoteStyle: "single"``); dotted i18n keys never contain single quotes,
    so plain wrapping is safe.
    """
    if isinstance(node, str):
        return f"'{node}'"
    if not isinstance(node, dict) or not node:
        return "{}"
    pad = "  " * indent
    inner_pad = "  " * (indent + 1)
    lines = ["{"]
    for k in sorted(node.keys()):
        key_repr = k if _is_valid_js_identifier(k) else f"'{k}'"
        lines.append(f"{inner_pad}{key_repr}: {_serialize(node[k], indent=indent + 1)},")
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def _is_valid_js_identifier(name: str) -> bool:
    """True if ``name`` can be an unquoted object key in JS (ASCII subset)."""
    if not name or not (name[0].isalpha() or name[0] in "_$"):
        return False
    return all(c.isalnum() or c in "_$" for c in name)
