"""Semantic, read-only checks for upgrades in host-owned migration histories."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


@dataclass(frozen=True, kw_only=True)
class DataCompatibilityIssue:
    """An outstanding module upgrade, independent of Alembic revision ids."""

    upgrade_id: str
    message: str
    severity: Literal["warning", "error"]

    def remediation(self) -> str:
        return f"smpy migrations prepare {self.upgrade_id} --head <host-head-or-label@head>"


async def collect_data_compatibility(
    modules: Sequence[ModuleBase], db: Any
) -> list[DataCompatibilityIssue]:
    """Read module state without applying migrations or changing credentials."""
    issues = []
    for module in modules:
        issues.extend(await module.check_data_compatibility(db))
    return issues
