"""Domain events published by the Tenants module.

These are the seams a billing module hangs off: create the customer on
``TenantCreated``, sync seat counts on ``MembershipAdded``/``MembershipRemoved``,
and drive ``TenantStatusChanged`` itself through ``TenantService.set_status``.
Published after the unit of work commits, so a handler never sees a row that
was rolled back.
"""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class TenantCreated(Event):
    tenant_id: str
    slug: str
    name: str
    owner_user_id: str


@dataclass
class TenantStatusChanged(Event):
    tenant_id: str
    status: str
    previous: str


@dataclass
class MembershipAdded(Event):
    tenant_id: str
    user_id: str
    role: str


@dataclass
class MembershipRemoved(Event):
    tenant_id: str
    user_id: str


@dataclass
class InvitationCreated(Event):
    """Delivery hook: a mailer module sends ``accept_url`` to ``email``.

    ``accept_url`` is absolute only when the ``public_base_url`` setting is
    set; otherwise it is root-relative and the mailer must prefix its origin.
    """

    tenant_id: str
    tenant_name: str
    email: str
    role: str
    accept_url: str
