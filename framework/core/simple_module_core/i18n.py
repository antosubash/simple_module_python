"""Internationalization registry and translator."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from babel import Locale

logger = logging.getLogger(__name__)

#: CLDR plural categories, in spec order. Used both for runtime resolution and
#: as the exhaustive suffix set when tools (e.g. the frontend-types emitter)
#: need to detect plural-variant keys.
PLURAL_CATEGORIES: tuple[str, ...] = ("zero", "one", "two", "few", "many", "other")


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
    except Exception:
        return "other"
    return rule(count)


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
        self._sources: list[tuple[str, Path, str]] = []
        self._messages: dict[str, dict[str, str]] = {}
        # Immutable views into ``_messages`` — handed out by ``messages()`` to
        # avoid a per-call dict copy. Rebuilt whenever ``load()`` runs.
        self._message_views: dict[str, MappingProxyType[str, str]] = {}
        # Plain-dict snapshots for JSON-serializing callers (e.g. Inertia shared
        # props). Built once per load; handing the same dict out on every request
        # avoids per-request dict copies that used to dominate allocations on the
        # Inertia render path.
        self._message_snapshots: dict[str, dict[str, str]] = {}
        self._public_snapshots: dict[str, dict[str, str]] = {}
        self._available_locales: tuple[str, ...] = ()
        self._available_locales_list: list[str] = []
        self._empty_view: MappingProxyType[str, str] = MappingProxyType({})
        self._empty_snapshot: dict[str, str] = {}
        self._loaded = False

    def add_source(self, namespace: str, locale_dir: Path, *, audience: str = "public") -> None:
        """Queue a module's locale directory for loading under a namespace.

        ``audience="admin"`` keeps the namespace out of the public snapshot
        (:meth:`messages_snapshot` with ``include_admin=False``) so catalogs
        for login-gated UI aren't shipped to anonymous visitors. Server-side
        lookups (:meth:`messages`) always see every namespace.
        """
        self._sources.append((namespace, Path(locale_dir), audience))

    def load(self) -> None:
        """Read and flatten all registered JSON files.

        Missing <locale>.json files for declared supported_locales log a
        warning but do not raise. Malformed JSON raises ValueError.
        """
        self._messages = {locale: {} for locale in self.supported_locales}
        public_messages: dict[str, dict[str, str]] = {
            locale: {} for locale in self.supported_locales
        }

        for namespace, locale_dir, audience in self._sources:
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
                if audience != "admin":
                    public_messages[locale].update(flat)

        # Cache the derived views now that loading is complete. Downstream
        # (middleware, translator, switcher) reads these on every request.
        self._message_views = {
            locale: MappingProxyType(msgs) for locale, msgs in self._messages.items()
        }
        # Plain-dict snapshots for serialization callers. ``dict(msgs)`` runs
        # once here rather than on every Inertia render. The public variant
        # (admin namespaces excluded) is what anonymous visitors receive.
        self._message_snapshots = {locale: dict(msgs) for locale, msgs in self._messages.items()}
        self._public_snapshots = public_messages
        self._available_locales = tuple(locale for locale, msgs in self._messages.items() if msgs)
        self._available_locales_list = list(self._available_locales)
        self._loaded = True

    def available_locales(self) -> list[str]:
        """Locales that have at least one loaded message.

        The list is cached at ``load()`` time; if ``load()`` hasn't run but
        tests populated ``_messages`` directly, a one-off scan returns the
        derived list without caching it (the test is outside the normal flow).
        """
        if self._loaded:
            return self._available_locales_list
        return [locale for locale, msgs in self._messages.items() if msgs]

    def messages(self, locale: str) -> Mapping[str, str]:
        """Flat dotted-key map for the given locale. Empty mapping if unknown.

        Returns an immutable view (``MappingProxyType``) into the cached
        message dict — zero-copy. Callers that JSON-serialize the result
        should use :meth:`messages_snapshot` instead.
        """
        view = self._message_views.get(locale)
        if view is not None:
            return view
        # Fallback: ``load()`` wasn't called (tests may populate _messages
        # directly). Expose the raw dict as a proxy so Translator still works.
        raw = self._messages.get(locale)
        if raw is None:
            return self._empty_view
        return MappingProxyType(raw)

    def messages_snapshot(self, locale: str, *, include_admin: bool = True) -> dict[str, str]:
        """Plain-dict snapshot for callers that JSON-serialize the result.

        Built once at :meth:`load` time and handed out by reference on every
        call. Callers must treat it as read-only — mutating the returned dict
        corrupts subsequent responses. Used by the Inertia shared-props builder
        where it sits on the request hot path; prior to this method,
        ``dict(messages(locale))`` per request was the top own-code allocator.

        ``include_admin=False`` returns the variant without ``audience="admin"``
        namespaces — what anonymous visitors are served.
        """
        pool = self._message_snapshots if include_admin else self._public_snapshots
        snapshot = pool.get(locale)
        if snapshot is not None:
            return snapshot
        # Fallback for tests that skip ``load()``: synthesize the snapshot on
        # demand from whatever ``_messages`` holds (audience information only
        # exists for sources that went through ``load()``).
        raw = self._messages.get(locale)
        if raw is None:
            return self._empty_snapshot
        return dict(raw)


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
