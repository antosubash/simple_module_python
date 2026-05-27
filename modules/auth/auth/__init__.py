"""Auth module — shared contracts (UserContext, AuthProvider, PrincipalResolver, deps)."""

from auth.contracts.provider import AuthProvider
from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext

__all__ = ["AuthProvider", "PrincipalResolver", "UserContext"]
