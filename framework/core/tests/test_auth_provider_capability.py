"""Public auth capability and the dated legacy marker fallback (#960)."""

import warnings

from simple_module_core.diagnostics._module import ModuleDiagnostics
from simple_module_core.diagnostics._types import DiagnosticLevel
from simple_module_core.discovery import select_auth_provider
from simple_module_core.module import ModuleBase, ModuleMeta


def test_legacy_marker_warns_once_across_selection_and_diagnostics():
    class Legacy(ModuleBase):
        meta = ModuleMeta(name="Legacy")
        _is_auth_provider = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        legacy = Legacy()
        assert select_auth_provider([legacy]) == [legacy]
        assert ModuleDiagnostics()._check_auth_provider_conflict([legacy]) == []
        assert select_auth_provider([Legacy()])[0].meta.name == "Legacy"

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert "0.1.0" in str(caught[0].message)
    assert "provides_auth=True" in str(caught[0].message)


def test_legacy_and_public_providers_participate_in_selection_and_sm020():
    class Legacy(ModuleBase):
        meta = ModuleMeta(name="Legacy")
        _is_auth_provider = True

    class Public(ModuleBase):
        meta = ModuleMeta(name="Public", provides_auth=True)

    modules = [Legacy(), Public()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert select_auth_provider(modules, "public") == [modules[1]]
        (finding,) = ModuleDiagnostics()._check_auth_provider_conflict(modules)
    assert finding.code == "SM020"
    assert finding.level == DiagnosticLevel.ERROR
    assert "Legacy" in finding.message and "Public" in finding.message


def test_structural_provider_without_declaration_warns():
    class Undeclared(ModuleBase):
        meta = ModuleMeta(name="Undeclared")
        name = "undeclared"

        async def resolve_user(self, request):
            return None

        def get_login_url(self, request, next_url=None):
            return "/login"

        def get_logout_url(self, request):
            return "/logout"

        def is_bearer_request(self, request):
            return False

    findings = ModuleDiagnostics()._check_auth_provider_conflict([Undeclared()])
    (finding,) = [d for d in findings if d.code == "SM020"]
    assert finding.level == DiagnosticLevel.WARNING
    assert finding.module_name == "Undeclared"
    assert "provides_auth=True" in finding.suggestion
