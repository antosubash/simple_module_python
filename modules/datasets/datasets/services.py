"""Module-scoped state container for the Datasets module.

Stored as ``app.state.datasets`` by
:meth:`DatasetsModule.register_settings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datasets.settings import DatasetsSettings
    from datasets.storage import LocalDatasetStorage


@dataclass
class DatasetsServices:
    """Datasets module singletons."""

    settings: DatasetsSettings
    storage: LocalDatasetStorage
