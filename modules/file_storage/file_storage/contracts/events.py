"""file_storage domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class FileUploaded(Event):
    file_id: uuid.UUID
    key: str
    backend: str
    size_bytes: int
    uploaded_by: str | None


@dataclass
class FileDeleted(Event):
    file_id: uuid.UUID
    key: str
