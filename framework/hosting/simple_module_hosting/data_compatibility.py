"""Enforce module data compatibility before hydrated settings and startup."""

import logging
from collections.abc import Sequence

from fastapi import FastAPI
from simple_module_core.data_compatibility import collect_data_compatibility
from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)


class DataCompatibilityError(RuntimeError):
    """An incompatible security state must also keep the setup gate closed."""


async def check_data_compatibility(app: FastAPI, modules: Sequence[ModuleBase]) -> None:
    try:
        async with app.state.sm.db.session_factory() as db:
            issues = await collect_data_compatibility(modules, db)
    except Exception as exc:
        raise DataCompatibilityError("Could not check module data compatibility") from exc
    errors = []
    for issue in issues:
        message = f"{issue.upgrade_id}: {issue.message} Prepare: {issue.remediation()}"
        logger.warning(message)
        if issue.severity == "error":
            errors.append(message)
    if errors and app.state.sm.settings.environment != "development":
        raise DataCompatibilityError("Data compatibility upgrade required:\n" + "\n".join(errors))
