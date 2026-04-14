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
    tenant_id: str | None = None

    @classmethod
    def from_keycloak_userinfo(cls, userinfo: dict) -> UserContext:
        """Create from Keycloak's userinfo dict (stored in session).

        Tenant is resolved from the ``tenant_id`` claim (custom Keycloak
        protocol mapper) or from the Keycloak organization payload.
        """
        tenant_id = userinfo.get("tenant_id")
        if tenant_id is None:
            # Fall back to Keycloak organization claim (Keycloak 25+)
            org = userinfo.get("organization")
            if isinstance(org, dict):
                tenant_id = org.get("id")

        return cls(
            id=userinfo.get("sub", ""),
            email=userinfo.get("email", ""),
            name=userinfo.get("name", userinfo.get("preferred_username", "")),
            roles=userinfo.get("realm_access", {}).get("roles", []),
            tenant_id=tenant_id,
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: list[str]) -> bool:
        return bool(set(self.roles) & set(roles))
