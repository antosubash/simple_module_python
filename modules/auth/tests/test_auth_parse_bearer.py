"""``parse_bearer``: the one place an ``Authorization: Bearer`` header is read (GH #533)."""

from __future__ import annotations

import pytest
from auth.contracts.tokens import parse_bearer


@pytest.mark.parametrize(
    "header",
    ["Bearer abc", "bearer abc", "BEARER abc", "BeArEr abc", "  Bearer   abc  ", "bearer\tabc"],
)
def test_scheme_is_case_insensitive_and_whitespace_tolerant(header):
    assert parse_bearer(header) == "abc"


@pytest.mark.parametrize(
    "header", [None, "", "Bearer", "Bearer   ", "Basic abc", "Bearerabc", "Token abc"]
)
def test_anything_else_is_not_a_bearer_credential(header):
    assert parse_bearer(header) is None
