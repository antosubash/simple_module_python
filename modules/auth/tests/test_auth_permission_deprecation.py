"""The legacy any-of permission helper carries a migration warning (#698)."""

import pytest
from auth.deps import require_permission
from simple_module_core.deprecation import registered_deprecations


def test_auth_require_permission_warns_and_registers_removal():
    with pytest.warns(DeprecationWarning, match="RequiresPermission"):
        dependency = require_permission("products.view")
    assert callable(dependency.dependency)
    entry = next(d for d in registered_deprecations() if d.name == "auth.deps.require_permission")
    assert entry.remove_in == "0.1.0"
