"""Domain events emitted by the Datasets module.

Events carry the handful of fields subscribers most often route on
(``slug``, ``kind``) so downstream handlers don't have to make a round
trip to ``IDatasetService`` just to decide whether the event is for
them. Anything beyond this — CRS, bbox, feature counts — is still a
``get_by_id`` away.
"""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class DatasetUploaded(Event):
    dataset_id: int
    name: str
    slug: str
    kind: str


@dataclass
class DatasetDeleted(Event):
    dataset_id: int
    slug: str
