"""Auth data types shared with other modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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

    @classmethod
    def from_user(cls, user: User | Any) -> UserContext:
        """Build a UserContext from a users.models.User with eagerly-loaded roles.

        Duck-typed to avoid importing users.models at runtime — any object
        exposing .id, .email, .full_name, .roles[*].name, .tenant_id works.
        The caller is responsible for eager-loading roles (selectinload).
        """
        return cls(
            id=str(user.id),
            email=user.email,
            name=user.full_name or user.email,
            roles=[r.name for r in user.roles],
            tenant_id=user.tenant_id,
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
            )
        except (KeyError, TypeError, ValueError):
            return None

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: list[str]) -> bool:
        return bool(set(self.roles) & set(roles))
