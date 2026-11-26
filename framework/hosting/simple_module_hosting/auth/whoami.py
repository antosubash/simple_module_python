"""Return the authenticated principal's identity to API clients."""

from fastapi import APIRouter, Depends, Request
from simple_module_core.access.tenancy import tenant_slug
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
    tenant_slug: str | None = None
    roles: list[str]


@router.get("/whoami", dependencies=[Depends(Authenticated()), Depends(TokenAllowed())])
async def whoami(request: Request) -> WhoAmI:
    """Identify the credential and principal authenticated for this request."""
    user = request.state.user
    # The slug names the tenant the request really acts for: the one the tenancy layer
    # validated (request.state.tenant_id), and only when it is the principal's own claim.
    resolved = getattr(request.state, "tenant_id", None)
    slug = None
    if user.tenant_id and resolved == user.tenant_id:
        slug = await tenant_slug(request.app, user.tenant_id)
    return WhoAmI(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_kind=user.auth_kind,
        scopes=user.scopes,
        tenant_id=user.tenant_id,
        tenant_slug=slug,
        roles=user.roles,
    )
