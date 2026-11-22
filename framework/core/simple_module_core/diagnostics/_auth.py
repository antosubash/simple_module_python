"""SM020/SM021 — declared auth providers and detectable undeclared ones."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel
from simple_module_core.modules._auth_providers import provides_auth, resembles_auth_provider

if TYPE_CHECKING:
    from simple_module_core.modules.module import ModuleBase


def check_auth_providers(modules: list[ModuleBase]) -> list[Diagnostic]:
    providers = [m for m in modules if provides_auth(m)]
    diags: list[Diagnostic] = []
    for mod in modules:
        if not provides_auth(mod) and resembles_auth_provider(mod):
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM020",
                    message=f"Module '{mod.meta.name}' resembles an undeclared AuthProvider",
                    module_name=mod.meta.name,
                    suggestion="Declare ModuleMeta(provides_auth=True) for provider selection",
                )
            )
    if len(providers) > 1:
        names = ", ".join(m.meta.name for m in providers)
        diags.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SM020",
                message=f"Multiple auth provider modules installed: {names}",
                module_name=providers[0].meta.name,
                suggestion="Select one provider with SM_AUTH_PROVIDER or enable only one",
            )
        )
    elif not providers:
        diags.append(
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM021",
                message="No auth provider module installed",
                module_name="(none)",
                suggestion=(
                    "Install an auth provider module "
                    "(e.g. 'simple-module-users' or 'simple-module-keycloak')"
                ),
            )
        )
    return diags
