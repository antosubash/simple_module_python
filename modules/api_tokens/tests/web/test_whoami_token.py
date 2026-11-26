from _api_tokens_support import create_pat


async def test_whoami_pat(actor, bearer):
    scopes = ["api_tokens.use"]
    async with actor() as user:
        token = (await create_pat(user.client, scopes))["token"]
        response = await bearer("GET", "/api/_meta/whoami", token)
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == user.user_id
        assert body["auth_kind"] == "pat"
        assert body["scopes"] == scopes
        assert body["tenant_id"] == user.tenant_id


async def test_whoami_reports_the_tenant_slug(app, actor, bearer):
    from sqlalchemy import select
    from tenants.models import Tenant

    async with actor() as user:
        token = (await create_pat(user.client, ["api_tokens.use"]))["token"]
        body = (await bearer("GET", "/api/_meta/whoami", token)).json()
        async with app.state.sm.db.session_factory() as db:
            stmt = select(Tenant.slug).where(Tenant.id == body["tenant_id"])
            slug = (await db.execute(stmt)).scalar()
        assert slug and body["tenant_slug"] == slug
