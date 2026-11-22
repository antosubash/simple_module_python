"""Semantic, read-only checks for upgrades in host-owned migration histories."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from simple_module_core.migrations.support import data_upgrade_entry_points

if TYPE_CHECKING:
    from simple_module_core.modules.module import ModuleBase


@dataclass(frozen=True, kw_only=True)
class DataCompatibilityIssue:
    """An outstanding module upgrade, independent of Alembic revision ids."""

    upgrade_id: str
    message: str
    severity: Literal["warning", "error"]
    remediation_text: str | None = None

    def remediation(self) -> str | None:
        if self.remediation_text is not None:
            return self.remediation_text
        if len(data_upgrade_entry_points().select(name=self.upgrade_id)) == 1:
            return f"smpy migrations prepare {self.upgrade_id} --head <host-head-or-label@head>"
        return None


async def collect_data_compatibility(
    modules: Sequence[ModuleBase], db: Any
) -> list[DataCompatibilityIssue]:
    """Read module state without applying migrations or changing credentials."""
    issues = []
    for module in checking_modules(modules):
        issues.extend(await module.check_data_compatibility(db))
    return issues


def checking_modules(modules: Sequence[ModuleBase]) -> list[ModuleBase]:
    """Modules that override the hook; the rest need no database session."""
    from simple_module_core.modules.module import ModuleBase

    return [
        module
        for module in modules
        if type(module).check_data_compatibility is not ModuleBase.check_data_compatibility
    ]
