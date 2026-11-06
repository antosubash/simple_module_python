"""Byte counts as a human reads them, for copy the server composes.

Mirrors ``pages/format.ts`` so the limit named in a rejected upload's message
reads the same as the limit printed under the drop zone that accepted it. Kept
in the module rather than the framework: nothing outside file_storage has a
byte count to write into a sentence yet.
"""

from __future__ import annotations

import math

_UNITS: tuple[tuple[int, str], ...] = (
    (1024**3, "GB"),
    (1024**2, "MB"),
    (1024, "KB"),
)


def format_bytes(count: int) -> str:
    """``"18 KB"``, ``"840 KB"``, ``"1.2 GB"`` — one decimal, never ``".0"``.

    A 25 MB limit reads as "25 MB"; only a value that genuinely needs the
    precision spends a character on it.
    """
    for scale, unit in _UNITS:
        if count >= scale:
            return f"{_round(count / scale)} {unit}"
    return f"{count} B"


def _round(value: float) -> str:
    """One decimal, rounded half *up* and with a bare ``.0`` dropped.

    Half-up rather than :func:`round`, whose banker's rounding turns 1.25 MB
    into "1.2 MB" where the TypeScript twin says "1.3 MB". Two numbers for one
    limit is exactly the confusion this message exists to remove.
    """
    whole, tenth = divmod(math.floor(value * 10 + 0.5), 10)
    return str(whole) if tenth == 0 else f"{whole}.{tenth}"
