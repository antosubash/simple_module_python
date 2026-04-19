"""Module-scoped state container for the GisDatasets module.

Stored as ``app.state.gis_datasets`` by
:meth:`GisDatasetsModule.register_settings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gis_datasets.settings import GisDatasetsSettings
    from gis_datasets.storage import LocalDatasetStorage


@dataclass
class GisDatasetsServices:
    """GisDatasets module singletons."""

    settings: GisDatasetsSettings
    storage: LocalDatasetStorage
