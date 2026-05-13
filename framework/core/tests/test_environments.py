"""Sanity check for the shared NON_PROD_ENVIRONMENTS constant.

A single source of truth is the whole point of this module — both host and
module settings validators read this. If anyone reverts to a duplicated
literal, the production placeholder-secret check could diverge between host
and modules and silently let an insecure deployment boot.
"""

from __future__ import annotations

from simple_module_core.environments import NON_PROD_ENVIRONMENTS


def test_contains_development_and_testing():
    assert "development" in NON_PROD_ENVIRONMENTS
    assert "testing" in NON_PROD_ENVIRONMENTS


def test_does_not_contain_production_aliases():
    """Nothing prod-like should be treated as non-prod."""
    for name in ("production", "prod", "staging", "live", ""):
        assert name not in NON_PROD_ENVIRONMENTS


def test_is_frozenset():
    """Freezing makes it tamper-proof — code that does
    ``NON_PROD_ENVIRONMENTS.add("staging")`` to "fix" their deployment will
    blow up at import time instead of widening the security envelope.
    """
    assert isinstance(NON_PROD_ENVIRONMENTS, frozenset)
