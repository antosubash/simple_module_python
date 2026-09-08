"""``format_bytes`` must read the same as its TypeScript twin.

The drop zone says "max 100 MB" from ``pages/format.ts`` and a rejected upload
says the limit from ``format.py``. Two spellings of one number in two places on
one screen is worse than not naming it at all, so the cases below are the ones
``tests-js/format.test.ts`` asserts, transcribed.
"""

from __future__ import annotations

import pytest
from file_storage.format import format_bytes

KIB = 1024
MIB = KIB * KIB
GIB = MIB * KIB


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (KIB, "1 KB"),
        (MIB - 1, "1024 KB"),
        (MIB, "1 MB"),
        (100 * MIB, "100 MB"),
        (round(1.2 * GIB), "1.2 GB"),
    ],
)
def test_matches_the_typescript_twin(count: int, expected: str) -> None:
    assert format_bytes(count) == expected


def test_rounds_a_half_away_from_zero() -> None:
    """Python's banker's rounding would say "1.2 MB" where the deck says 1.3."""
    assert format_bytes(round(1.25 * MIB)) == "1.3 MB"
