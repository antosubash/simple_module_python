"""Domain events emitted by the Datasets module."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class DatasetUploaded(Event):
    dataset_id: int
    name: str
    kind: str


@dataclass
class DatasetDeleted(Event):
    dataset_id: int
