"""Sample pytest-benchmark suite.

Run via ``make bench``. Gated by the ``benchmark`` marker so the default
``pytest`` run skips these. Use this file as a template — each benchmark is
a plain sync test that calls the ``benchmark`` fixture on the code under
test and lets pytest-benchmark handle round/warmup selection.
"""

from __future__ import annotations

import pytest
from simple_module_test import forge_session_cookie

pytestmark = pytest.mark.perf


def test_forge_session_cookie(benchmark):
    """Signing a session cookie is on every authenticated request's hot path."""
    secret = "bench-secret-key"
    payload = {"user_id": "00000000-0000-0000-0000-000000000001"}

    result = benchmark(forge_session_cookie, secret, payload)

    assert isinstance(result, str) and result
