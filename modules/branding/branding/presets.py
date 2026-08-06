"""Built-in branding presets — a look an administrator can apply in one click.

Mirrors IIASA.GeoWiki's ``BrandingPresets`` + ``ApplyPresetAsync``: a named
bundle of branding values, applied through the ordinary update path so every
validator still runs.

**A preset carries appearance, never identity.** GeoWiki's presets set the brand
name and tagline because each one *is* a specific tenant (Global Canopy Atlas,
Forest Observation System). Here the module ships with a generic app, so a
preset that overwrote ``app_name`` — or a logo an admin had just uploaded —
would destroy exactly the work the branding page exists to do. Presets are
therefore restricted to :data:`PRESET_FIELDS`.

Not an extension point: like the reference, the list is fixed in the module. A
module wanting its own look ships a *design pack* instead, which is the
registry-backed, module-contributed mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

#: Branding settings a preset is allowed to touch. Everything else — the app
#: name, the uploaded images, the announcement banner — is deployment identity
#: or operational state, and survives applying a preset.
PRESET_FIELDS: Final = frozenset({"primary_color", "design_pack"})


@dataclass(frozen=True)
class BrandingPreset:
    """One named, one-click look."""

    key: str
    label: str
    #: Subset of :data:`PRESET_FIELDS` to apply.
    values: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.values) - PRESET_FIELDS
        if unknown:
            raise ValueError(
                f"Preset {self.key!r} sets non-preset field(s) {sorted(unknown)}; "
                f"presets may only set {sorted(PRESET_FIELDS)}"
            )

    @property
    def swatch(self) -> str | None:
        """Colour to show in the picker, when the preset sets one."""
        return self.values.get("primary_color")


# Ordered: the first entry restores the framework default.
BUILTIN_PRESETS: Final[tuple[BrandingPreset, ...]] = (
    BrandingPreset("emerald", "Emerald", {"primary_color": "#10b981"}),
    BrandingPreset("ocean", "Ocean", {"primary_color": "#0ea5e9"}),
    BrandingPreset("indigo", "Indigo", {"primary_color": "#6366f1"}),
    BrandingPreset("violet", "Violet", {"primary_color": "#8b5cf6"}),
    BrandingPreset("amber", "Amber", {"primary_color": "#f59e0b"}),
    BrandingPreset("rose", "Rose", {"primary_color": "#f43f5e"}),
    BrandingPreset("slate", "Slate", {"primary_color": "#64748b"}),
)


def find_preset(key: str) -> BrandingPreset | None:
    """Look up a preset by key, or ``None`` if no such preset ships."""
    return next((p for p in BUILTIN_PRESETS if p.key == key), None)
