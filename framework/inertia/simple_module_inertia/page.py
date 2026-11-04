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
        ("rescuedProps", resolved.rescued),
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


_JSON_LEAVES = frozenset({str, int, float, bool, type(None)})


def _is_plain_json(value: Any) -> bool:
    """True when ``value`` is built only from exact JSON types.

    Exact ``type()`` checks keep subclasses (``StrEnum``, ``IntEnum``) on the
    ``jsonable_encoder`` path, which converts them; plain data, such as the
    shared i18n catalog, skips a full encoder walk that costs about 5x a
    ``json.dumps`` of the same dict.
    """
    stack = [value]
    while stack:
        item = stack.pop()
        kind = type(item)
        if kind is dict:
            for key, child in item.items():
                if type(key) is not str:
                    return False
                stack.append(child)
        elif kind is list:
            stack.extend(item)
        elif kind not in _JSON_LEAVES:
            return False
    return True


def encode_page(page: dict[str, Any]) -> Any:
    """JSON-safe structure for both render branches; names the failing prop."""
    if _is_plain_json(page):
        return page
    try:
        return jsonable_encoder(page)
    except Exception as exc:
        raise PropEncodingError(_locate_failure(page["props"], "props"), exc) from exc
