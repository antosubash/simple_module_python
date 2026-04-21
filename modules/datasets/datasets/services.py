"""Module-scoped state container for the Datasets module.

Stored as ``app.state.datasets`` by :meth:`DatasetsModule.register_settings`.
The storage backend is not held here — it lives on
``app.state.file_storage.backend`` (owned by the ``file_storage`` module)
and is fetched lazily per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datasets.settings import DatasetsSettings


@dataclass
class DatasetsServices:
    """Datasets module singletons."""

    settings: DatasetsSettings
