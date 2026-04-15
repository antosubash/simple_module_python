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
