"""Request-scoped translator and CLDR plural resolution."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from babel import Locale

if TYPE_CHECKING:
    from simple_module_core.i18n import I18nRegistry

# Logged under the historical ``simple_module_core.i18n`` name so existing log
# filters keep matching after the split.
logger = logging.getLogger("simple_module_core.i18n")
_plural_failure_warned = False


@lru_cache(maxsize=64)
def _plural_rule(locale: str):
    """Cached CLDR plural rule for a locale tag (e.g. 'en', 'ru', 'pt_BR')."""
    return Locale.parse(locale).plural_form


def _plural_form(locale: str, count: float) -> str:
    """Return CLDR plural category ('one', 'few', 'many', 'other', ...).

    Falls back to 'other' if the locale cannot be parsed by Babel.
    """
    try:
        rule = _plural_rule(locale)
    except Exception:
        global _plural_failure_warned
        if not _plural_failure_warned:
            _plural_failure_warned = True
            logger.warning("Plural locale parsing failed; using other", exc_info=True)
        return "other"
    return rule(count)


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

    def _lookup(self, key: str) -> str | None:
        msgs = self._registry.messages(self.locale)
        if key in msgs:
            return msgs[key]
        if self.locale != self.default_locale:
            default = self._registry.messages(self.default_locale)
            if key in default:
                return default[key]
        return None
