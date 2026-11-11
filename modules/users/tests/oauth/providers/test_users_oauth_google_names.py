"""Google sign-in asks the People API for the name too (#877)."""

from users.oauth.google import GoogleWithNames
from users.oauth.providers import OAuthProvider


async def test_google_profile_requests_names_and_fills_display_name(httpx_mock):
    httpx_mock.add_response(
        json={
            "resourceName": "people/1",
            "names": [{"displayName": "Jane Doe"}],
            "emailAddresses": [
                {"value": "jane@example.com", "metadata": {"primary": True, "verified": True}}
            ],
        }
    )
    provider = OAuthProvider("google", "Google", GoogleWithNames("id", "secret"))

    identity = await provider.get_identity({"access_token": "t"})

    assert identity.display_name == "Jane Doe"
    assert identity.email_verified is True
    request = httpx_mock.get_request()
    assert request.url.params["personFields"] == "emailAddresses,names"
