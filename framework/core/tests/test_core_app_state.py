"""Optional app services retain their defaults and installed object identity."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core import app_state


@pytest.mark.parametrize(
    ("attribute", "accessor_name", "default"),
    [
        ("sm", "get_services", None),
        ("host", "get_host_services", None),
        ("public_routes", "get_public_routes", None),
        ("body_limits", "get_body_limits", None),
        ("rate_limit_rules", "get_rate_limit_rules", None),
        ("design_packs", "get_design_packs", None),
        ("migration", "get_migration_status", None),
        ("openapi_url", "get_openapi_url", None),
        ("spa_prefixes", "get_spa_prefixes", ()),
        ("deferred_startup", "get_deferred_startup", None),
        ("deferred_startup_lock", "get_deferred_startup_lock", None),
        ("principal_serializer", "get_principal_serializer", None),
        ("tenant_resolver", "get_tenant_resolver", None),
        ("tenant_exists", "get_tenant_exists", None),
        ("tenant_members", "get_tenant_members", None),
        ("inertia_dependency", "get_inertia_dependency", None),
        ("inertia_shared_providers", "get_inertia_shared_providers", None),
        ("branding", "get_branding", None),
        ("auth", "get_auth_provider", None),
    ],
)
def test_core_optional_app_service(attribute, accessor_name, default):
    app = FastAPI()
    accessor = getattr(app_state, accessor_name)
    assert accessor(app) == default

    installed = object()
    value = SimpleNamespace(auth_provider=installed) if attribute == "auth" else installed
    setattr(app.state, attribute, value)
    assert accessor(app) is installed

    setattr(app.state, attribute, None)
    assert accessor(app) is None


def test_core_partial_auth_state_has_no_provider():
    app = FastAPI()
    app.state.auth = SimpleNamespace()
    assert app_state.get_auth_provider(app) is None


def test_core_optional_scope_app_can_lack_state():
    assert app_state.get_services(None) is None
    assert app_state.get_services(SimpleNamespace()) is None
    assert app_state.get_tenant_resolver(None) is None
