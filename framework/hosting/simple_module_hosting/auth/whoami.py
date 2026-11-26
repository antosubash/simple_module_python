"""Return the authenticated principal's identity to API clients."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import SQLModel

from simple_module_hosting.auth.token_guard import Authenticated, TokenAllowed

router = APIRouter(prefix="/api/_meta", tags=["Meta"])


class WhoAmI(SQLModel):
    id: str
    email: str
    name: str
    auth_kind: str
    scopes: list[str] | None
    tenant_id: str | None
    roles: list[str]


@router.get("/whoami", dependencies=[Depends(Authenticated()), Depends(TokenAllowed())])
async def whoami(request: Request) -> WhoAmI:
    """Identify the credential and principal authenticated for this request."""
    user = request.state.user
    return WhoAmI(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_kind=user.auth_kind,
        scopes=user.scopes,
        tenant_id=user.tenant_id,
        roles=user.roles,
    )
