async def test_whoami_session(authenticated_client):
    response = await authenticated_client.get("/api/_meta/whoami")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@test"
    assert body["auth_kind"] == "session"
    assert body["scopes"] is None


async def test_whoami_anonymous_401(client):
    assert (await client.get("/api/_meta/whoami")).status_code == 401


async def _whoami_slug(claim: str | None, resolved: str | None):
    from types import SimpleNamespace

    from simple_module_hosting.auth.whoami import whoami

    async def slug(tenant_id: str) -> str | None:
        return f"slug-of-{tenant_id}"

    user = SimpleNamespace(
        id="u", email="e", name="n", auth_kind="pat", scopes=[], tenant_id=claim, roles=[]
    )
    request = SimpleNamespace(
        state=SimpleNamespace(user=user, tenant_id=resolved),
        app=SimpleNamespace(state=SimpleNamespace(tenant_slug=slug)),
    )
    return (await whoami(request)).tenant_slug


async def test_slug_only_for_the_validated_tenant():
    assert await _whoami_slug("t1", "t1") == "slug-of-t1"
    assert await _whoami_slug("t1", None) is None  # the claim was rejected by tenancy
    assert await _whoami_slug("t1", "t2") is None
    assert await _whoami_slug(None, "t2") is None
