"""JSON snapshots for trusted static props, with byte-preserving page encoding."""

from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder

_HTML_ENCODER = json.JSONEncoder()
_RESPONSE_ENCODER = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class JsonSnapshot(dict):
    """Read-only-by-contract JSON data, encoded once for each response format.

    Like registry snapshots, callers must never mutate this dict. Keeping the
    dict interface preserves shared-prop consumers outside Inertia rendering.
    Only wrap trusted static data: dynamic props must go through resolution.
    """

    def __init__(self, value: dict) -> None:
        super().__init__(jsonable_encoder(value))
        self.html_json = _HTML_ENCODER.encode(self)
        self.response_json = _RESPONSE_ENCODER.encode(self)


def dumps(value: Any, *, compact: bool = False) -> str:
    """Splice the shared i18n catalog into page JSON using the original format.

    Only descend along props.i18n.messages. Other props keep the C encoder's
    fast path, including large lists. HTML escaping still happens afterwards
    in htmlsafe_json_dumps, covering the catalog and the rest of the page.
    """
    encoder = _RESPONSE_ENCODER if compact else _HTML_ENCODER

    def encode(item: Any, path: tuple[str, ...]) -> str:
        if isinstance(item, JsonSnapshot):
            return item.response_json if compact else item.html_json
        if not path or not isinstance(item, dict) or path[0] not in item:
            return encoder.encode(item)
        parts = []
        for key, child in item.items():
            if key == path[0]:
                parts.append(encoder.encode(key) + encoder.key_separator + encode(child, path[1:]))
            else:
                # Strip only this single-entry object's surrounding braces.
                parts.append(encoder.encode({key: child})[1:-1])
        return "{" + encoder.item_separator.join(parts) + "}"

    return encode(value, ("props", "i18n", "messages"))
