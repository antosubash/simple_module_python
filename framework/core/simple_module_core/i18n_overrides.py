"""Host overrides of module copy, keyed by full dotted path (#415).

``host/locales/overrides/<locale>.json`` is applied after every module,
framework and host catalog. An override replaces an existing key and never
creates one: a typo would otherwise invent a key nothing renders, and a new
key would churn the generated TypeScript key list. Audience is kept: a key
only an admin catalog defines stays out of the anonymous snapshot.
"""

from __future__ import annotations

from pathlib import Path

from simple_module_core._i18n_flatten import flatten_messages, read_catalog


def load_overrides(overrides_dir: Path, locale: str) -> dict[str, str]:
    """Flattened ``{dotted.key: text}`` from ``<overrides_dir>/<locale>.json``; ``{}`` if absent."""
    path = overrides_dir / f"{locale}.json"
    if not path.is_file():
        return {}
    return flatten_messages(read_catalog(path), prefix="")


def apply_overrides(
    overrides: dict[str, str],
    messages: dict[str, str],
    public: dict[str, str],
    *,
    default_messages: dict[str, str] | None = None,
    default_public: dict[str, str] | None = None,
) -> list[str]:
    """Apply ``overrides`` in place; return the keys that matched nothing.

    A key exists if this locale or the default locale defines it, so a
    translation of copy the locale has not translated yet still lands. The
    public map only gains a key that is public here or in the default locale,
    so an admin-only key never leaks.
    """
    unknown: list[str] = []
    for key, value in overrides.items():
        if key not in messages and key not in (default_messages or {}):
            unknown.append(key)
            continue
        messages[key] = value
        if key in public or key in (default_public or {}):
            public[key] = value
    return sorted(unknown)
