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

from dataclasses import dataclass

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
            (e.g. ``"/admin/users/{id}/edit"``).
        label: Human-readable name for the entity kind, shown instead of the
            raw class name (e.g. ``"User account"``).
    """

    entity_type: str
    url_template: str
    label: str = ""

    def __post_init__(self) -> None:
        if _ID_PLACEHOLDER not in self.url_template:
            raise ValueError(
                f"AuditLink for {self.entity_type!r} has url_template "
                f"{self.url_template!r}, which contains no {_ID_PLACEHOLDER} — "
                f"every row would link to the same page"
            )

    def url_for(self, entity_id: str) -> str:
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
