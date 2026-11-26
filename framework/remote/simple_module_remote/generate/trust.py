"""Which schema may relax a safety hint.

A live schema comes from the server, so it may only make the CLI more careful: its
``x-cli-confirm`` adds a confirmation, but only the bundled schema's ``x-cli-safe`` for
the same method and path template can waive the confirmation of a mutation on a
protected environment.
"""

from __future__ import annotations

from dataclasses import replace

from simple_module_remote.generate.operations import Operation, parse_operations

__all__ = ["HintIndex", "hint_index", "trusted_hints"]

HintIndex = dict[tuple[str, str], Operation]


def hint_index(bundled: dict) -> HintIndex:
    return {(op.method, op.path): op for op in parse_operations(bundled)}


def trusted_hints(op: Operation, index: HintIndex) -> Operation:
    """``op`` with ``safe`` taken from the bundled twin and ``confirm`` from either."""
    twin = index.get((op.method, op.path))
    return replace(
        op,
        safe=twin is not None and twin.safe,
        confirm=op.confirm or (twin is not None and twin.confirm),
    )
