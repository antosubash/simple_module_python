"""Audit-link registry — modules teach the audit log how to reach their records.

An audit entry stores the *model class name* and primary key of the row that
changed (``StoredFile``, ``a91f3c2b…`` — ``snapshot_changes`` records
``type(obj).__name__``, never ``__tablename__``). That is enough to prove what
happened and useless for doing anything about it: the reader has an id and no
way to open the record it names.

A module declares where its rows live via
:meth:`~simple_module_core.module.ModuleBase.register_audit_links`; the host
collects them into one registry at boot and stores it on
``app.state.sm.audit_links``.

**The registry maps model class names to URL templates, nothing more.** It does
not verify the row exists or that the reader may open it — following a link to a
deleted record lands on that screen's own 404, and permissions are enforced by
the target route as usual.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

LabelResolver = Callable[[Any, list[str]], Awaitable[dict[str, str]]]
"""Batch "what is this row called" for one entity type.

Called with the request's database session and every entity id of that type on
the page, and returns ``{entity_id: display name}``. Ids it cannot name are
simply absent — the caller falls back to the id, which is what the audit row
actually stored.

The session is typed ``Any`` because ``simple_module_core`` must not depend on
SQLAlchemy; in practice it is the ``AsyncSession`` the request is already
using, so a resolver adds one query per entity type per page and no session
management of its own.
"""

_ID_PLACEHOLDER = "{id}"


@dataclass(frozen=True)
class AuditLink:
    """Where the records of one audited model can be viewed.

    Args:
        entity_type: The **model class name**, matching
            ``AuditEntry.entity_type`` (e.g. ``"User"``, not ``"users_user"``).
            ``snapshot_changes`` records ``type(obj).__name__``, so keying this
            off ``__tablename__`` silently never matches — and because an
            unmatched lookup falls back to showing ``entity_type`` as the
            label, a table-name key looks like it worked.
        url_template: Path containing ``{id}``, substituted with the entity id
            (e.g. ``"/admin/users/{id}/edit"``). Empty means *these rows have
            no screen* — join tables and stored files are audited but have
            nowhere to open — and the cell renders the name unlinked. A module
            still registers those, because it is the only thing that knows what
            the table is called and what its rows are named.
        label: Human-readable name for the entity kind, shown instead of the
            raw class name (e.g. ``"User account"``).
        label_key: Catalog key for ``label``. Empty, or unresolved, falls back
            to ``label`` — a missing translation shows English rather than a
            raw dotted key. Rows are rendered server-side, so the audit view
            translates these before they reach the page.
        table_name: ``__tablename__`` of the table these rows live in
            (``"users_user"``), shown as the type tag beside the row's name.
            Not derivable from ``entity_type`` in either direction, so the
            module that owns the table states both. ``None`` falls back to the
            class name.
        label_resolver: Optional :data:`LabelResolver` naming individual rows.
            Without it a reader gets a primary key and has to paste it into
            another screen to learn which record changed; only the owning
            module knows that a ``Setting`` is named by its key and a ``User``
            by ``full_name or email``. Excluded from equality: it is typically
            a closure, and two boots would build two unequal objects out of one
            module — a registry conflict is about two modules claiming one
            entity type, which the identity fields already express.
    """

    entity_type: str
    url_template: str
    label: str = ""
    label_key: str = ""
    table_name: str | None = None
    label_resolver: LabelResolver | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.url_template and _ID_PLACEHOLDER not in self.url_template:
            raise ValueError(
                f"AuditLink for {self.entity_type!r} has url_template "
                f"{self.url_template!r}, which contains no {_ID_PLACEHOLDER} — "
                f"every row would link to the same page"
            )

    def url_for(self, entity_id: str) -> str | None:
        """The row's page, or ``None`` when this kind of row has no screen."""
        if not self.url_template:
            return None
        return self.url_template.replace(_ID_PLACEHOLDER, entity_id)


class AuditLinkRegistry:
    """Aggregates every module's :class:`AuditLink` declarations.

    Populated once during boot (``register_audit_links`` hook) and read
    thereafter by the audit log view when it renders each row.
    """

    def __init__(self) -> None:
        self._links: dict[str, AuditLink] = {}

    def register(self, link: AuditLink) -> None:
        existing = self._links.get(link.entity_type)
        if existing is not None and existing != link:
            raise ValueError(
                f"Two modules claim audit links for {link.entity_type!r}: "
                f"{existing.url_template!r} and {link.url_template!r}"
            )
        self._links[link.entity_type] = link

    def get(self, entity_type: str) -> AuditLink | None:
        return self._links.get(entity_type)

    @property
    def all_links(self) -> dict[str, AuditLink]:
        return dict(self._links)
