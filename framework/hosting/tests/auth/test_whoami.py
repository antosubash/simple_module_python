async def test_whoami_session(authenticated_client):
    response = await authenticated_client.get("/api/_meta/whoami")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@test"
    assert body["auth_kind"] == "session"
    assert body["scopes"] is None


async def test_whoami_anonymous_401(client):
    assert (await client.get("/api/_meta/whoami")).status_code == 401
