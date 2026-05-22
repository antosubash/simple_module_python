"""Auth module — shared contracts (UserContext, PrincipalResolver, deps)."""

from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext

__all__ = ["PrincipalResolver", "UserContext"]
