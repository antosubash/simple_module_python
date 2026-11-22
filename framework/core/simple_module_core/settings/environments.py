"""Shared environment-classification constants.

Both the host and module settings validators need to know which ``SM_ENVIRONMENT``
values are "non-prod" — anything outside this set is treated as production
and subject to stricter defaults (e.g. placeholder-secret rejection).

Duplicating this constant in each settings module would mean an operator who
adds ``"staging"`` to one list but forgets the other gets inconsistent
validation. Lives in ``simple_module_core`` because both the host package and
module settings already depend on it.
"""

from __future__ import annotations

NON_PROD_ENVIRONMENTS: frozenset[str] = frozenset({"development", "testing"})
