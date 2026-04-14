"""Auth data types shared with other modules."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserContext:
    """Authenticated user information extracted from Keycloak token."""

    id: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)

    @classmethod
    def from_keycloak_userinfo(cls, userinfo: dict) -> UserContext:
        """Create from Keycloak's userinfo dict (stored in session)."""
        return cls(
            id=userinfo.get("sub", ""),
            email=userinfo.get("email", ""),
            name=userinfo.get("name", userinfo.get("preferred_username", "")),
            roles=userinfo.get("realm_access", {}).get("roles", []),
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: list[str]) -> bool:
        return bool(set(self.roles) & set(roles))
