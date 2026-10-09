"""Host overrides of module copy, keyed by full dotted path (#415).

``host/locales/overrides/<locale>.json`` is applied after every module,
framework and host catalog. An override replaces an existing key and never
creates one: a typo would otherwise invent a key nothing renders, and a new
key would churn the generated TypeScript key list. Audience is kept: a key
only an admin catalog defines stays out of the anonymous snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_core._i18n_flatten import flatten_messages


def load_overrides(overrides_dir: Path, locale: str) -> dict[str, str]:
    path = overrides_dir / f"{locale}.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object at the top level")
    return flatten_messages(raw, prefix="")


def apply_overrides(
    overrides: dict[str, str], messages: dict[str, str], public: dict[str, str]
) -> list[str]:
    """Apply ``overrides`` in place; return the keys that matched nothing."""
    unknown: list[str] = []
    for key, value in overrides.items():
        if key not in messages:
            unknown.append(key)
            continue
        messages[key] = value
        if key in public:
            public[key] = value
    return sorted(unknown)
