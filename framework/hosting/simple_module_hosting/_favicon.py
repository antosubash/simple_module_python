"""The favicon an install has before anyone uploads one.

Without a default, ``index.html`` emitted no ``<link rel="icon">`` at all, so
every browser fell back to its implicit ``/favicon.ico`` request — which this
app does not route. Anonymous visitors got a 302 to the login page (an HTML
document offered as an image), authenticated ones a 404, and either way a
console error on every full page load, on a brand-new install that has done
nothing wrong.

Rendered as an SVG ``data:`` URI rather than a file so there is nothing to
mount, nothing to exempt from auth, and nothing to ship in the image: the
static mount is a build artifact (``host/static/dist`` is generated), and a
route would need its own public-route rule. ``img-src`` already allows
``data:``, so the strict CSP is untouched.

The mark mirrors ``BrandingMark``'s fallback badge — the app's initial on the
brand gradient — so the tab icon and the in-app logo are the same thing, for
whatever the app is named. An uploaded favicon still wins; this is only the
floor.
"""

from __future__ import annotations

from urllib.parse import quote

#: sRGB for `--color-primary-600` / `--color-primary-800`
#: (`oklch(0.59 0.14 158)` / `oklch(0.42 0.09 175)`), the two stops of
#: `BRAND_ACCENT`. Hard-coded because a data URI cannot read a CSS custom
#: property — kept beside the tokens they mirror in `ui/styles/globals.css`.
_ACCENT_FROM = "#00955c"
_ACCENT_TO = "#005c4a"

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="a" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="{from_}"/>'
    '<stop offset="1" stop-color="{to}"/>'
    "</linearGradient></defs>"
    '<rect width="64" height="64" rx="14" fill="url(#a)"/>'
    '<text x="32" y="45" text-anchor="middle" fill="#fff" font-size="34" '
    'font-weight="700" font-family="system-ui,-apple-system,Segoe UI,'
    'Roboto,sans-serif">{initial}</text>'
    "</svg>"
)


def default_favicon_data_uri(app_name: str, accent: str = "") -> str:
    """An SVG data URI showing ``app_name``'s initial on the brand gradient.

    ``accent`` is branding's configured primary colour: when set it replaces
    both gradient stops with the flat brand colour, so a customised install's
    tab icon matches the rest of its chrome. Already validated as a hex colour
    by ``BrandingSettings``; anything else is ignored rather than trusted into
    the markup.
    """
    initial = _initial(app_name)
    from_, to = (accent, accent) if _is_hex_colour(accent) else (_ACCENT_FROM, _ACCENT_TO)
    svg = _SVG.format(from_=from_, to=to, initial=initial)
    # Everything structural is encoded — `#` above all, or the browser reads
    # the gradient reference as the URI's fragment and the shape loses its
    # fill, but also `"`, `<`, `>` and spaces so the result stays a single
    # valid attribute value without relying on the template's escaping. The
    # safe set is only characters that are already legal unencoded in a URI.
    return "data:image/svg+xml," + quote(svg, safe="/:=,;()-_.'")


def _initial(app_name: str) -> str:
    """First character of the app name, XML-escaped, defaulting to ``S``.

    Matches ``BrandingMark``'s ``appName.trim().charAt(0).toUpperCase() || 'S'``
    so the tab and the sidebar badge never disagree.
    """
    raw = (app_name or "").strip()[:1].upper() or "S"
    return raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_hex_colour(value: str) -> bool:
    """Whether ``value`` is a ``#rgb``/``#rrggbb`` literal safe to interpolate."""
    if not value.startswith("#"):
        return False
    body = value[1:]
    return len(body) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in body)


__all__ = ["default_favicon_data_uri"]
