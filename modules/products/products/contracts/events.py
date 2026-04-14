"""Product domain events — published when product state changes."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class ProductCreated(Event):
    product_id: int
    name: str


@dataclass
class ProductUpdated(Event):
    product_id: int
    name: str


@dataclass
class ProductDeleted(Event):
    product_id: int
