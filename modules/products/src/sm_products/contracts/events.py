"""Product domain events — published when product state changes."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class ProductCreated(Event):
    """Published after a new product is persisted."""

    product_id: int
    name: str


@dataclass
class ProductUpdated(Event):
    """Published after an existing product is modified."""

    product_id: int
    name: str


@dataclass
class ProductDeleted(Event):
    """Published after a product is removed."""

    product_id: int
