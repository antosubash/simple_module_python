"""Values that keep a scaffolded app passing its own ``make lint`` (GH #896)."""

from __future__ import annotations

# ty is pre-1.0 and renames rules between releases (0.0.100 renamed
# ``unresolved-attribute``, which the scaffold's ``[tool.ty.rules]`` names), so
# new apps get the range this repo is tested on, not the newest ty.
# ``test_scaffold_lint_tooling.py`` fails once ``uv.lock`` moves past it.
TY_REQUIREMENT = "ty>=0.0.90,<0.0.100"

# Apps turn ty's ``invalid-assignment`` off, so this ignore would be reported as
# unused there; only a module inside the framework repo, which checks the rule,
# gets it.
MODEL_CONFIG_TY_IGNORE = "  # ty: ignore[invalid-assignment]"

_MODULE_CONSTANTS = (
    "API_PREFIX",
    "LOCALE_NAMESPACE",
    "MENU_ICON",
    "MENU_LABEL",
    "MENU_LABEL_KEY",
    "MENU_ORDER",
    "MENU_URL",
    "PERM_GROUP",
    "VIEW_PREFIX",
)
_MODULE_PERMISSIONS = ("CREATE", "DELETE", "EDIT", "VIEW")


def module_constants_import(package_upper: str) -> str:
    """The ``module.py`` constants import list, in the order ruff's isort wants.

    Where ``PERM_GROUP`` falls among ``PERM_<PACKAGE>_*`` depends on the package
    name, so a fixed template order is unsorted for half of all names.
    """
    names = [*_MODULE_CONSTANTS, *(f"PERM_{package_upper}_{p}" for p in _MODULE_PERMISSIONS)]
    return "\n".join(f"    {name}," for name in sorted(names, key=str.lower))
