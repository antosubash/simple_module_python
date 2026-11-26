"""Strip terminal control sequences from server-controlled text before it reaches a terminal."""

from __future__ import annotations

import re
from typing import TextIO

__all__ = ["is_terminal", "sanitize", "sanitize_for"]

_ESCAPES = re.compile(
    r"\x1b\][^\x07\x1b\x9c]*(?:\x07|\x1b\\|\x9c)?"  # OSC (titles, hyperlinks)
    r"|\x1b[PX^_][^\x1b\x9c]*(?:\x1b\\|\x9c)?"  # DCS, SOS, PM, APC strings
    r"|\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x1b[ -/]*[0-~]?"  # other escapes, incl. a lone ESC
)
# C0/C1 controls (not newline/tab), bidi overrides/isolates, line and paragraph separators.
_CONTROLS = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\u2028\u2029]")


def sanitize(text: str) -> str:
    """Remove ESC sequences and C0/C1 controls, keeping newline and tab."""
    return _CONTROLS.sub("", _ESCAPES.sub("", text))


def is_terminal(stream: TextIO) -> bool:
    check = getattr(stream, "isatty", None)
    return bool(check()) if callable(check) else False


def sanitize_for(stream: TextIO, text: str) -> str:
    """``text`` made safe for ``stream``: sanitized on a terminal, byte-exact otherwise."""
    return sanitize(text) if is_terminal(stream) else text
