"""The origin an admin-copied link is built on.

Links an admin copies in the browser (a password-reset link, an invite link
surfaced when mail could not be sent) used ``UsersSettings.base_url``, whose
default is the dev origin ``http://localhost:8000`` — so every install that had
not set it handed out links to localhost.

Precedence, most deliberate first:

1. ``users.base_url`` when an operator changed it — the origin the mailers use,
   so a copied link matches an emailed one.
2. ``HostSettings.public_base_url`` — the site's declared public origin.
3. The request's own base URL. Safe *here* and only here: the link goes back to
   the admin whose browser made this request, so its ``Host`` is the origin they
   are already using. Emails never take this path — a ``Host`` header must not
   pick where a link mailed to someone else points.
"""

from __future__ import annotations

from starlette.requests import Request

from users.settings import UsersSettings

_DEFAULT_BASE_URL = UsersSettings.model_fields["base_url"].default


def admin_link_base(request: Request) -> str:
    """The origin (no trailing slash) to build an admin-copied link on."""
    users = getattr(getattr(request.app.state, "users", None), "settings", None)
    configured = str(getattr(users, "base_url", "") or "")
    if configured and configured != _DEFAULT_BASE_URL:
        return configured.rstrip("/")
    host = getattr(getattr(request.app.state, "host", None), "settings", None)
    public = str(getattr(host, "public_base_url", "") or "")
    if public:
        return public.rstrip("/")
    return str(request.base_url).rstrip("/")
