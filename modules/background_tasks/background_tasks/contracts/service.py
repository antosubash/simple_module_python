"""Public service interface for the BackgroundTasks module.

Other modules depend on this Protocol, not on the concrete implementation.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from background_tasks.constants import TaskStatus
from background_tasks.contracts.schemas import (
    TaskExecutionDetail,
    TaskExecutionListResponse,
)


class IBackgroundTaskService(Protocol):
    """Surface exposed to callers outside the module."""

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        task_name: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> TaskExecutionListResponse: ...

    async def get(self, execution_id: uuid.UUID) -> TaskExecutionDetail | None: ...

    async def retry(self, execution_id: uuid.UUID) -> TaskExecutionDetail: ...
