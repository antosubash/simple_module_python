"""Tenant lifecycle contracts shared without a dependency on a tenant provider."""

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class TenantDeleted(Event):
    """The tenant registry row is gone; owners must durably tear down its data.

    Delivery is at least once. Retention stores may keep historical rows,
    identified by their original tenant id, but must never expose live resources.
    """

    tenant_id: str
    slug: str
    name: str
