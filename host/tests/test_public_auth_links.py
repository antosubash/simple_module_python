"""No page may link a visitor to ``/auth/...``.

``/auth`` is the JSON **API** prefix — ``/api/users/auth/login`` is a POST that
returns 204. The sign-in *page* lives at ``/users/login``, under the users
module's view prefix. The two look interchangeable in a template and are not:
the landing page's "Get started" and "Sign up" buttons, and all four of
``PublicLayout``'s, pointed at ``/auth/login`` and every one of them 404'd —
which is every public entry point into the app.

The paths are one-way: nothing outside the users module should be spelling
either of them inline, so this test also keeps them funnelled through
``lib/auth-routes.ts``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_DIRS = ("host/client_app", "packages/ui/src", "modules")

# href/to="/auth/anything" — an href, not an API call inside a fetch().
_AUTH_HREF = re.compile(r"""(?:href|to)=\{?["'`]/auth/""")

_SKIP_DIRS = {"node_modules", "dist", "build", ".vite", "__pycache__"}


def _tsx_sources() -> list[Path]:
    files: list[Path] = []
    for rel in _SOURCE_DIRS:
        base = _ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.tsx"):
            if _SKIP_DIRS.isdisjoint(path.parts):
                files.append(path)
    return files


def test_sources_exist_to_scan() -> None:
    """Guard the guard: a bad glob would make every assertion below vacuous."""
    assert len(_tsx_sources()) > 20


def test_no_page_links_to_the_api_auth_prefix() -> None:
    offenders = [
        f"{path.relative_to(_ROOT)}:{n}"
        for path in _tsx_sources()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _AUTH_HREF.search(line)
    ]
    assert not offenders, (
        "These link a visitor to the JSON API prefix, which has no page behind "
        "it and renders 404. Use LOGIN_PATH / REGISTER_PATH from "
        f"packages/ui/src/lib/auth-routes.ts instead: {offenders}"
    )


def _declared_path(constant: str) -> str:
    source = (_ROOT / "packages/ui/src/lib/auth-routes.ts").read_text(encoding="utf-8")
    match = re.search(rf"export const {constant} = '([^']+)';", source)
    assert match, f"{constant} is not declared in lib/auth-routes.ts"
    return match.group(1)


def _users_meta():
    from simple_module_core.discovery import discover_modules

    for module in discover_modules():
        if module.meta.name.lower() == "users":
            return module.meta
    pytest.fail("users module not installed; cannot verify auth paths")


@pytest.mark.parametrize(
    ("constant", "route"),
    [("LOGIN_PATH", "login"), ("REGISTER_PATH", "register")],
)
def test_auth_route_constants_track_the_users_view_prefix(constant: str, route: str) -> None:
    """Derived, not hardcoded: if the module's view prefix moves, this fails.

    Hardcoding ``/users/login`` here would let the prefix change out from under
    the constants and still pass — which is precisely the drift being guarded.
    """
    assert _declared_path(constant) == f"{_users_meta().view_prefix}/{route}"


def test_users_admin_path_tracks_the_admin_view_prefix() -> None:
    """User management moved out from under the module's own view prefix.

    Sign-in is a public page and belongs on ``/users``; managing accounts is an
    admin screen and belongs with the others under ``/admin``. One module, two
    mount points — so this constant tracks ``admin_view_prefix``, not
    ``view_prefix``, and would drift silently if it were spelled out here.
    """
    # Trailing slash: the index is registered at "/" under the prefix, so the
    # slashed form is the canonical path. Linking to the bare one costs a 307
    # on every navigation — see test_menu_urls_are_canonical.
    assert _declared_path("USERS_ADMIN_PATH") == f"{_users_meta().admin_view_prefix}/"
