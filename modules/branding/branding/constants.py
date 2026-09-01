"""Branding module constants."""

from __future__ import annotations

import re
from typing import Final

from simple_module_core.design_packs import SLUG_RE

ROUTE_PREFIX: Final = "/api/branding"
VIEW_PREFIX: Final = "/admin/branding"
# Trailing slash: the browse route is registered at "/" under VIEW_PREFIX, so
# linking to the bare prefix costs a 307 round trip on every navigation.
MENU_URL: Final = f"{VIEW_PREFIX}/"

PACKAGE: Final = "branding"

# Modules this one depends on (kept as constants so the depends_on list doesn't
# carry bare string literals — see scripts/check_hardcoded_strings.py).
_MODULE_SETTINGS: Final = "Settings"
_MODULE_FILE_STORAGE: Final = "FileStorage"

# Inertia page identifier. The view endpoint renders this as a literal (so the
# SM003/SM004 static-AST diagnostics can pair it with pages/Manage.tsx); a test
# asserts the literal matches this constant.
_PAGE_MANAGE: Final = "Branding/Manage"

PERM_VIEW: Final = "branding.view"
PERM_MANAGE: Final = "branding.manage"

# A #rrggbb hex colour (single source of truth for both the settings and the
# update-DTO validators).
HEX_COLOR_RE: Final = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_APP_NAME_LEN: Final = 60

# ── Site-wide announcement banner ──────────────────────────────────────
# An empty message hides the banner entirely; severity drives its colour.
MAX_BANNER_MESSAGE_LEN: Final = 500
BANNER_SEVERITY_INFO: Final = "info"
BANNER_SEVERITIES: Final = (BANNER_SEVERITY_INFO, "warning", "danger")
BANNER_SEVERITY_ERROR: Final = f"banner_severity must be one of {', '.join(BANNER_SEVERITIES)}"


def normalize_banner_severity(value: str | None) -> str:
    """Coerce a severity to a known value, falling back to ``info``.

    Used by the *settings* validator rather than the DTO: settings hydrate from
    the DB, where a hand-edited or since-removed severity must degrade to a
    readable banner instead of refusing to boot. The update DTO rejects unknown
    values outright so the API gives a clear 422.
    """
    candidate = (value or "").strip().lower()
    return candidate if candidate in BANNER_SEVERITIES else BANNER_SEVERITY_INFO


def clean_banner_message(value: str) -> str:
    """Trim + bound the banner text (shared by the settings and update DTO)."""
    cleaned = value.strip()
    if len(cleaned) > MAX_BANNER_MESSAGE_LEN:
        raise ValueError(f"banner_message must be at most {MAX_BANNER_MESSAGE_LEN} characters")
    return cleaned


# A design-pack slug. Aliased from the framework's own pattern so branding and
# DesignPack can never disagree about what a valid slug is.
DESIGN_PACK_RE: Final = SLUG_RE
DESIGN_PACK_ERROR: Final = (
    "design_pack must be a lowercase slug (letters, digits and dashes, "
    "not starting with a dash) or empty"
)

# Image upload guard-rails live in branding.images (allow-list, size ceiling and
# magic-number sniffing), which owns the whole "is this really an image?" question.

# ── Public asset routes ────────────────────────────────────────────────
# Branding serves its own logo and favicon instead of linking file_storage's
# download route, which is gated by ``file-storage.download``. No logged-out
# request carries that permission, and the sign-in page, the public landing
# page and every ``<link rel="icon">`` are exactly where the logo has to show.
# Only the two ids currently stored in branding settings are served here, so
# this is not a way to read arbitrary files out of file_storage.
#: One-click look. ``{key}`` names a preset from ``branding.presets``.
PATH_PRESET: Final = "/presets/{key}"

PATH_LOGO: Final = "/logo"
PATH_LOGO_DARK: Final = "/logo-dark"
PATH_FAVICON: Final = "/favicon"
LOGO_URL: Final = ROUTE_PREFIX + PATH_LOGO
LOGO_DARK_URL: Final = ROUTE_PREFIX + PATH_LOGO_DARK
FAVICON_URL: Final = ROUTE_PREFIX + PATH_FAVICON

# Cache policy, mirroring IIASA.GeoWiki's BrandingImageCache. The published URL
# carries ``?v=<file_id>``, and a replaced image is a *new* file_storage id — so
# a versioned request is content-addressed and safe to pin for a year. A request
# without a usable version must never be immutable: that same URL can serve new
# bytes later, so it gets a short cache and self-corrects.
ASSET_VERSION_QUERY_KEY: Final = "v"
ASSET_MAX_AGE_VERSIONED: Final = 365 * 24 * 60 * 60
ASSET_MAX_AGE_UNVERSIONED: Final = 60 * 60


def clean_app_name(value: str) -> str:
    """Normalise + validate an app name (shared by the settings + update DTO).

    The name is surfaced in HTML titles and—critically—email ``Subject``
    headers, so control characters (notably CR/LF) must be rejected: an
    embedded newline would otherwise pass a bare ``strip()`` and then raise
    when set as a header, breaking every transactional email.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("app_name must not be blank")
    if len(cleaned) > MAX_APP_NAME_LEN:
        raise ValueError(f"app_name must be at most {MAX_APP_NAME_LEN} characters")
    if any(ord(ch) < 0x20 for ch in cleaned):
        raise ValueError("app_name must not contain control characters")
    return cleaned


# ── Footer links ───────────────────────────────────────────────────────
# An empty list means "use the framework's own links" (`BRAND_FOOTER_LINKS`
# in @simple-module-py/ui), so an existing deployment that never sets these
# keeps the footer it has today.
MAX_FOOTER_LINKS: Final = 6
MAX_FOOTER_LINK_LABEL_LEN: Final = 40
MAX_FOOTER_LINK_HREF_LEN: Final = 500

#: Schemes an admin-supplied footer href may use, plus site-relative paths.
#:
#: This is a real allow-list, not tidiness: the href is rendered straight into
#: an ``<a href>`` on every page of the site, signed-in or not, so
#: ``javascript:`` (and ``data:``) would turn the branding screen into a stored
#: XSS sink for anyone holding ``branding.manage``.
FOOTER_LINK_SCHEMES: Final = ("http://", "https://", "mailto:")
FOOTER_LINK_HREF_ERROR: Final = (
    "footer link href must start with " + ", ".join(FOOTER_LINK_SCHEMES) + " or /"
)
#: Backslashes are rejected outright. Browsers normalise ``\`` to ``/`` in the
#: authority position of a special-scheme URL, so ``/\evil.example.com`` reads
#: as a site-relative path but navigates to ``https://evil.example.com`` — the
#: exact bypass the ``//host`` rule below exists to close. No legitimate footer
#: target needs a raw backslash; ``%5C`` still works for one in a path.
FOOTER_LINK_BACKSLASH_ERROR: Final = "footer link href must not contain a backslash"


def clean_footer_label(value: str) -> str:
    """Normalise + validate a footer link's visible text."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("footer link label must not be blank")
    if len(cleaned) > MAX_FOOTER_LINK_LABEL_LEN:
        raise ValueError(
            f"footer link label must be at most {MAX_FOOTER_LINK_LABEL_LEN} characters"
        )
    if any(ord(ch) < 0x20 for ch in cleaned):
        raise ValueError("footer link label must not contain control characters")
    return cleaned


def clean_footer_href(value: str) -> str:
    """Normalise + validate a footer link's target.

    Scheme-relative ``//host`` is rejected along with everything else outside
    the allow-list: it reads as a relative path but navigates off-site, so
    allowing it would make the ``/`` rule mean something other than "this site".
    Backslashes go with it — a browser reads ``/\\host`` the same way.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("footer link href must not be blank")
    if len(cleaned) > MAX_FOOTER_LINK_HREF_LEN:
        raise ValueError(f"footer link href must be at most {MAX_FOOTER_LINK_HREF_LEN} characters")
    if any(ord(ch) < 0x20 for ch in cleaned):
        raise ValueError("footer link href must not contain control characters")
    if "\\" in cleaned:
        raise ValueError(FOOTER_LINK_BACKSLASH_ERROR)
    lowered = cleaned.lower()
    relative = cleaned.startswith("/") and not cleaned.startswith("//")
    if not relative and not lowered.startswith(FOOTER_LINK_SCHEMES):
        raise ValueError(FOOTER_LINK_HREF_ERROR)
    return cleaned
