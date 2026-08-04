"""Design-pack registry — modules contribute a selectable look for the public site.

A *design pack* is a stylesheet a module ships that restyles the reader-facing
site by overriding the base design tokens beneath a ``<value>-root`` class. A
module declares the packs it provides via
:meth:`~simple_module_core.module.ModuleBase.register_design_packs`; the host
collects them into one registry at boot and stores it on
``app.state.design_packs``.

**The registry supplies the dropdown, not the stylesheet.** A pack's CSS still
reaches the bundle through the host's ``styles.css`` importing it by package
specifier. The registry's only job is to stop an administrator selecting a pack
that no installed module provides — which would otherwise put a class on the
document with nothing behind it and silently do nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
"""A pack slug: lowercase alphanumerics and dashes, not starting with a dash.

The site root class is ``f"{value}-root"``, so the slug has to be usable as a
bare CSS identifier fragment.
"""


@dataclass(frozen=True)
class DesignPack:
    """One selectable look.

    Args:
        value: Slug identifying the pack. The public site's root element
            carries ``f"{value}-root"``, which is the hook the pack's own
            stylesheet selects on.
        label: Human-readable name, shown in the branding dropdown.
    """

    value: str
    label: str

    def __post_init__(self) -> None:
        if not SLUG_RE.match(self.value):
            raise ValueError(
                f"DesignPack value {self.value!r} is not a usable class-name "
                f"fragment; it must match {SLUG_RE.pattern}"
            )


class DesignPackRegistry:
    """Aggregates every module's :class:`DesignPack` declarations.

    Populated once during boot (``register_design_packs`` hook) and read
    thereafter — by the branding view to build its dropdown, and by the
    branding API to validate a submitted slug.
    """

    def __init__(self) -> None:
        self._packs: dict[str, DesignPack] = {}

    def register(self, pack: DesignPack) -> None:
        """Add *pack*, rejecting a slug another module already claimed.

        Duplicate slugs are an error rather than a silent overwrite: two packs
        sharing one root class would leave whichever stylesheet happened to
        load last in charge, which is not something an administrator could
        diagnose from the UI.
        """
        existing = self._packs.get(pack.value)
        if existing is not None:
            raise ValueError(
                f"Design pack {pack.value!r} is already registered "
                f"(as {existing.label!r}); slugs must be unique across modules"
            )
        self._packs[pack.value] = pack

    def all(self) -> list[DesignPack]:
        """Every registered pack, in registration order (a copy)."""
        return list(self._packs.values())

    def has(self, value: str) -> bool:
        """Return ``True`` if some module registered a pack with this slug."""
        return value in self._packs


__all__ = ["DesignPack", "DesignPackRegistry"]
