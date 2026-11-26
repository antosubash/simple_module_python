"""Which schema may relax a safety hint.

A live schema comes from the server, so it may only make the CLI more careful: its
``x-cli-confirm`` adds a confirmation, but only the bundled schema's ``x-cli-safe`` for
the same method and path template can waive the confirmation of a mutation on a
protected environment. Templates are compared with placeholder names erased
(``/a/{x}`` is ``/a/{id}``), so a renamed placeholder neither gains nor loses a hint.
"""

from __future__ import annotations

import re
from dataclasses import replace

from simple_module_remote.generate.operations import Operation, parse_operations

__all__ = ["HintIndex", "hint_index", "route_key", "trusted_hints"]

_PLACEHOLDER = re.compile(r"\{[^}]*\}")
HintIndex = dict[tuple[str, str], list[Operation]]


def route_key(method: str, path: str) -> tuple[str, str]:
    """A route's identity: method plus the template with placeholder names erased."""
    return method.upper(), _PLACEHOLDER.sub("{}", path)


def hint_index(bundled: dict) -> HintIndex:
    index: HintIndex = {}
    for op in parse_operations(bundled):
        index.setdefault(route_key(op.method, op.path), []).append(op)
    return index


def trusted_hints(op: Operation, index: HintIndex) -> Operation:
    """``op`` with ``safe`` from its bundled twin(s) and ``confirm`` from either side."""
    twins = index.get(route_key(op.method, op.path), [])
    return replace(
        op,
        safe=bool(twins) and all(t.safe for t in twins),
        confirm=op.confirm or any(t.confirm for t in twins),
    )
