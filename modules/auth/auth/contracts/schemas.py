"""Auth data types shared with other modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from auth.contracts.tokens import AUTH_KIND_SESSION

if TYPE_CHECKING:
    # Runtime import would be circular: auth -> users -> auth.
    # Only imported for type-hints, never at runtime.
    from users.models import User


@dataclass
class UserContext:
    """Authenticated user information for downstream handlers."""

    id: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    # Permissions the principal carries itself — a token scope or IdP claim a
    # provider maps in. Frozen in the session cookie like ``roles``; anything
    # revocable belongs in a grant source. The resolver drops ``*`` from here.
    permissions: list[str] = field(default_factory=list)
    # Which credential authenticated the request: ``"session"`` for a browser
    # sign-in, ``"bearer"`` for a provider's own bearer token (a ``users``
    # access token, an IdP JWT), ``"pat"`` / ``"service"`` for an
    # ``api_tokens`` credential (see ``auth.contracts.tokens``). Code that must
    # only ever act for a person at a keyboard — minting more credentials —
    # refuses anything but ``"session"``.
    auth_kind: str = AUTH_KIND_SESSION
    # The ceiling a token carries. ``None`` means "no cap" (an ordinary
    # session); a list — even an empty one — is intersected with whatever the
    # principal resolves to, and the admin-role shortcuts are skipped, so an
    # admin's token is worth exactly the scopes it was given.
    scopes: list[str] | None = None

    @property
    def is_scoped(self) -> bool:
        """Whether a scope cap applies (any token-authenticated principal)."""
        return self.scopes is not None

    @classmethod
    def from_user(
        cls,
        user: User | Any,
        *,
        auth_kind: str = AUTH_KIND_SESSION,
        scopes: list[str] | None = None,
    ) -> UserContext:
        """Build a UserContext from a users.models.User with eagerly-loaded roles.

        Duck-typed to avoid importing users.models at runtime — any object
        exposing .id, .email, .full_name, .roles[*].name works. The user row
        carries no tenant: the active tenant is resolved per request from
        ``tenants_membership``, so ``tenant_id`` stays ``None`` here (only a
        generic provider's claim path sets it).
        The caller is responsible for eager-loading roles (selectinload).
        """
        return cls(
            id=str(user.id),
            email=user.email,
            name=user.full_name or user.email,
            roles=[r.name for r in user.roles],
            auth_kind=auth_kind,
            scopes=list(scopes) if scopes is not None else None,
        )

    def to_session_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for the signed session cookie.

        The inverse of :meth:`from_session_dict`. Adding a new field to
        ``UserContext`` requires updating both methods here — not the
        AuthMiddleware cache helper, which stays schema-agnostic."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "roles": list(self.roles),
            "tenant_id": self.tenant_id,
            "permissions": list(self.permissions),
            "auth_kind": self.auth_kind,
            "scopes": list(self.scopes) if self.scopes is not None else None,
        }

    @classmethod
    def from_session_dict(cls, payload: Any) -> UserContext | None:
        """Rebuild from :meth:`to_session_dict` output. Returns ``None`` on any
        shape mismatch so callers can fall through to a fresh DB load."""
        if not isinstance(payload, dict):
            return None
        try:
            return cls(
                id=str(payload["id"]),
                email=str(payload["email"]),
                name=str(payload["name"]),
                roles=list(payload.get("roles") or []),
                tenant_id=payload.get("tenant_id"),
                # Absent on cookies written before the field existed.
                permissions=list(payload.get("permissions") or []),
                auth_kind=str(payload.get("auth_kind") or AUTH_KIND_SESSION),
                scopes=_scopes_from(payload.get("scopes")),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """Exact match against :attr:`permissions` only — no roles, no wildcard.

        Gate routes with ``RequiresPermission``, which also folds in roles and
        grant sources; this is for the principal's own claims alone."""
        return permission in self.permissions

    def has_any_role(self, roles: list[str]) -> bool:
        return bool(set(self.roles) & set(roles))


def _scopes_from(raw: Any) -> list[str] | None:
    """``None`` stays ``None`` (uncapped); anything else must be a list."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise TypeError("scopes must be a list")
    return [str(s) for s in raw]
