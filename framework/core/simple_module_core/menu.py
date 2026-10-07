"""Menu system — modules contribute menu items, filtered by user roles."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger(__name__)

MenuItemMethod = Literal["get", "post"]


class MenuSection(StrEnum):
    """Where the menu item appears in the UI."""

    SIDEBAR = "sidebar"
    ADMIN_SIDEBAR = "adminSidebar"
    NAVBAR = "navbar"
    USER_DROPDOWN = "userDropdown"


@dataclass(frozen=True)
class MenuItem:
    """A single navigation entry."""

    label: str
    url: str
    label_key: str = ""
    """Catalog key for ``label``. Empty = ship ``label`` verbatim.

    Menu labels are rendered on every page, so they are translated on the
    server — the payload carries finished text and every render site (sidebar,
    topbar, command palette) keeps working untouched. A key that resolves to
    nothing falls back to ``label``, so a missing translation degrades to
    English rather than to a raw dotted key on screen.
    """
    icon: str = ""
    order: int = 0
    section: MenuSection = MenuSection.SIDEBAR
    requires_auth: bool = True
    roles: list[str] = field(default_factory=list)
    """Empty list = visible to all authenticated users."""
    permissions: list[str] = field(default_factory=list)
    """Permission keys required to see this entry. Empty = no permission check.

    Declare the same permission the target route enforces. Roles alone cannot
    express this: a custom role holding ``settings.view`` should see Settings,
    and hard-coding ``roles=["admin"]`` would hide it from them while still
    showing it to any admin-adjacent role that cannot actually open it. An
    entry that 403s on click is worse than no entry at all.
    """
    method: MenuItemMethod = "get"
    """HTTP method used when the item is activated. ``"post"`` renders as an
    Inertia form submission so the target endpoint can be POST-only (e.g. logout)."""
    group_key: str = ""
    """Catalog key for ``group``, with the same fallback rule as ``label_key``.

    Group headers are shared vocabulary — several modules file entries under
    "Administration" — so they live in the ``ui`` namespace. Letting each
    module invent its own key would let one translation drift from another and
    split a single header in two.
    """
    group: str = ""
    """Sidebar group label. Empty = ungrouped (renders flat, no header).
    Items in the same section that share a group are visually clustered under a
    header in the order they already sort by ``order``; the group's own position
    is set by the lowest-ordered item that belongs to it."""


MenuProvider = Callable[["Request"], "Awaitable[Iterable[MenuItem]] | Iterable[MenuItem]"]
"""Per-request source of menu items; sync or async."""


class MenuRegistry:
    """Collects menu items from all modules and filters them per-request."""

    def __init__(self) -> None:
        self._items: list[MenuItem] = []
        self._sorted: list[MenuItem] | None = None
        self._providers: list[MenuProvider] = []

    def _invalidate(self) -> None:
        self._sorted = None

    def add(self, item: MenuItem) -> None:
        self._items.append(item)
        self._invalidate()

    def add_many(self, items: list[MenuItem]) -> None:
        self._items.extend(items)
        self._invalidate()

    def remove(self, predicate: Callable[[MenuItem], bool]) -> int:
        """Drop static items for which *predicate* is true; return how many."""
        kept = [i for i in self._items if not predicate(i)]
        removed = len(self._items) - len(kept)
        self._items = kept
        self._invalidate()
        return removed

    def add_provider(self, provider: MenuProvider) -> None:
        """Register a per-request provider of extra menu items.

        Evaluated inside ``InertiaLayoutDataMiddleware`` (auth and
        ``request.state.tenant_id`` already resolved) and then filtered,
        translated, ordered and grouped like static items. A provider that
        raises is logged and contributes nothing.
        """
        self._providers.append(provider)

    async def collect_provider_items(self, request: Request) -> list[MenuItem]:
        items: list[MenuItem] = []
        for provider in self._providers:
            try:
                result = provider(request)
                if inspect.isawaitable(result):
                    result = await result
                # Materialise first: a generator failing midway must add nothing.
                items.extend(list(result))
            except Exception:
                logger.exception("Menu provider %r failed; contributing nothing", provider)
        return items

    @property
    def all_items(self) -> list[MenuItem]:
        if self._sorted is None:
            self._sorted = sorted(self._items, key=lambda i: i.order)
        return self._sorted

    async def get_for_request(
        self,
        request: Request,
        *,
        is_authenticated: bool,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        translate: Callable[[str], str] | None = None,
    ) -> dict[str, list[dict]]:
        """:meth:`get_for_user` over static items plus this request's provider items."""
        extra = await self.collect_provider_items(request) if self._providers else []
        return self.get_for_user(
            is_authenticated=is_authenticated,
            roles=roles,
            permissions=permissions,
            translate=translate,
            extra_items=extra,
        )

    def get_for_user(
        self,
        *,
        is_authenticated: bool,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        translate: Callable[[str], str] | None = None,
        extra_items: Iterable[MenuItem] = (),
    ) -> dict[str, list[dict]]:
        """Return menu items grouped by section, filtered by auth/roles/permissions.

        ``permissions`` is the caller's already-expanded permission list (no
        wildcards). Items declaring permissions the caller lacks are dropped,
        so the sidebar never offers a screen that will 403 on click.

        ``translate`` resolves ``label_key``/``group_key`` against the request's
        locale. Omitting it (or omitting the keys) ships the literal ``label``
        and ``group``, which is what third-party modules predating the keys do.

        Returns a dict ready to be serialized into Inertia shared props.
        """
        roles = roles or []
        granted = set(permissions or [])
        result: dict[str, list[dict]] = {s.value: [] for s in MenuSection}

        def render(key: str, fallback: str) -> str:
            # Translator.t() echoes the key back when the catalog has no entry.
            # Showing "users.nav.users" in the sidebar would be worse than the
            # English it replaced, so an unresolved key keeps the literal.
            if not key or translate is None:
                return fallback
            translated = translate(key)
            return fallback if translated == key else translated

        items = self.all_items
        if extra := list(extra_items):
            items = sorted([*items, *extra], key=lambda i: i.order)
        for item in items:
            if item.requires_auth and not is_authenticated:
                continue
            if item.roles and not any(r in item.roles for r in roles):
                continue
            # All declared permissions must be held: an entry naming several is
            # asking for all of them, matching how route guards compose.
            if item.permissions and not granted.issuperset(item.permissions):
                continue
            result[item.section.value].append(
                {
                    "label": render(item.label_key, item.label),
                    "url": item.url,
                    "icon": item.icon,
                    "method": item.method,
                    "group": render(item.group_key, item.group),
                }
            )

        return result
