"""Serialized catalogs owned by a registry and replaced with its snapshots."""

from weakref import WeakKeyDictionary

from simple_module_core.i18n import I18nRegistry
from simple_module_inertia._json_snapshot import JsonSnapshot

_catalogs: WeakKeyDictionary[
    I18nRegistry, dict[tuple[str, bool], tuple[dict[str, str], JsonSnapshot]]
] = WeakKeyDictionary()


def catalog_json(registry: I18nRegistry, locale: str, *, include_admin: bool) -> JsonSnapshot:
    snapshot = registry.messages_snapshot(locale, include_admin=include_admin)
    try:
        pool = _catalogs.setdefault(registry, {})
    except TypeError:
        # A stub registry (``__slots__``, unhashable dataclass) cannot key a weak
        # dict; serve it uncached rather than fail the request.
        return JsonSnapshot(snapshot)
    key = (locale, include_admin)
    cached = pool.get(key)
    # load() replaces snapshots: identity is the catalog version, without a hash
    # or a walk of the catalog on the request path.
    if cached is None or cached[0] is not snapshot:
        cached = (snapshot, JsonSnapshot(snapshot))
        pool[key] = cached
    return cached[1]
