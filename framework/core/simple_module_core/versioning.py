"""Framework API version compatibility checks for modules."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from simple_module_core.exceptions import FrameworkVersionError
from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)

FRAMEWORK_API_VERSION = "1.0.0"
"""Current public API version of simple_module_core.

Modules declare a compatible range via ``ModuleMeta.requires_framework``
(PEP 440 specifier, e.g. ``">=1.0,<2.0"``). Bumping this constant's major
component signals a breaking change in the module contract — ``ModuleBase``,
registries, the event bus, ``create_module_base``, or the model mixins.
"""

# Pre-parsed for the default compatibility check so boot doesn't re-parse
# this constant on every call. The custom-version path below still parses
# caller-supplied strings lazily.
_FRAMEWORK_VERSION = Version(FRAMEWORK_API_VERSION)


def check_framework_compatibility(
    modules: Sequence[ModuleBase],
    framework_version: str = FRAMEWORK_API_VERSION,
) -> None:
    """Fail fast if any module's ``requires_framework`` spec rejects the framework version.

    Modules with ``requires_framework=None`` are skipped (unversioned modules pass).
    Malformed specifiers are reported as failures rather than letting a cryptic
    ``InvalidSpecifier`` bubble up from deep inside ``packaging``.
    """
    current = (
        _FRAMEWORK_VERSION
        if framework_version == FRAMEWORK_API_VERSION
        else Version(framework_version)
    )
    failures: list[tuple[str, str, str]] = []

    for mod in modules:
        spec_str = mod.meta.requires_framework
        if spec_str is None:
            continue
        try:
            spec = SpecifierSet(spec_str)
        except InvalidSpecifier as exc:
            failures.append((mod.meta.name, spec_str, f"invalid version specifier ({exc})"))
            continue
        if current not in spec:
            failures.append(
                (
                    mod.meta.name,
                    spec_str,
                    f"framework {framework_version} does not satisfy '{spec_str}'",
                )
            )

    if failures:
        raise FrameworkVersionError(framework_version, failures)
