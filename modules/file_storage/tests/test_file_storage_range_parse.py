"""``Range`` header parsing (#453): single ranges only, RFC 9110 semantics."""

from __future__ import annotations

import pytest
from file_storage.ranges import UNSATISFIABLE, ByteRange, parse_range

SIZE = 1000


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-16383", ByteRange(0, 999)),  # end clamped to size - 1
        ("bytes=0-0", ByteRange(0, 0)),
        ("bytes=10-19", ByteRange(10, 19)),
        ("bytes=990-", ByteRange(990, 999)),
        ("bytes=-10", ByteRange(990, 999)),
        ("bytes=-5000", ByteRange(0, 999)),  # suffix longer than the object
        ("BYTES = 5 - 9 ", ByteRange(5, 9)),  # unit is case-insensitive
        ("bytes=999-999", ByteRange(999, 999)),
    ],
)
def test_satisfiable_ranges(header, expected):
    assert parse_range(header, SIZE) == expected


@pytest.mark.parametrize(
    "header", ["bytes=1000-", "bytes=1000-2000", "bytes=-0", "bytes=5000-6000"]
)
def test_unsatisfiable_ranges(header):
    assert parse_range(header, SIZE) == UNSATISFIABLE


def test_any_range_of_an_empty_object_is_unsatisfiable():
    assert parse_range("bytes=0-", 0) == UNSATISFIABLE
    assert parse_range("bytes=-1", 0) == UNSATISFIABLE


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "bytes=0-1,5-6",  # multi-range: ignored, full 200
        "items=0-1",
        "bytes",
        "bytes=",
        "bytes=-",
        "bytes=5-1",  # last < first is invalid syntax
        "bytes=-1-2",
        "bytes=a-b",
        "bytes=+1-2",
        "bytes=0x10-",
        "bytes=" + "9" * 20 + "-",  # absurdly long number
    ],
)
def test_ignored_headers(header):
    assert parse_range(header, SIZE) is None


def test_byte_range_length_is_inclusive():
    assert ByteRange(0, 16383).length == 16384
