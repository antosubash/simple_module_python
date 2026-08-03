"""Design packs — modules contribute site themes, branding picks one.

A pack is a CSS bundle scoped to a root class, so a site adopts it by adding
one class near the top of the document rather than by every component knowing
about it.

The registry holds only the value and the label. The stylesheet itself reaches
the browser through the host's own CSS entry point, exactly like any other
module stylesheet — this is not an asset pipeline. Its job is to stop an
administrator selecting a pack that no installed module provides, and to give
the branding UI something to put in a dropdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class DesignPack:
    """A selectable site theme."""

    value: str
    """Slug. The site root class is ``f"{value}-root"``."""

    label: str
    """Human-readable name, shown in the branding dropdown."""


class DesignPackRegistry:
    """Collects the design packs contributed by all modules."""

    def __init__(self) -> None:
        self._packs: dict[str, DesignPack] = {}

    def register(self, pack: DesignPack) -> None:
        """Add a pack.

        Raises:
            ValueError: if ``pack.value`` is not usable as a CSS class name, or
                if another module already registered that value.
        """
        if not _VALUE_RE.match(pack.value):
            raise ValueError(
                f"design pack value {pack.value!r} must match {_VALUE_RE.pattern} "
                "— it is interpolated into a CSS class name"
            )
        existing = self._packs.get(pack.value)
        if existing is not None:
            # Both packs would scope their CSS to the same root class, so the
            # winner would be whichever stylesheet the host imported last.
            raise ValueError(
                f"design pack {pack.value!r} is already registered as "
                f"{existing.label!r}; two packs cannot share a root class"
            )
        self._packs[pack.value] = pack

    def all(self) -> list[DesignPack]:
        """Every registered pack, ordered by label for display."""
        return sorted(self._packs.values(), key=lambda pack: pack.label.lower())

    def values(self) -> set[str]:
        """The registered slugs, for validating a submitted selection."""
        return set(self._packs)
