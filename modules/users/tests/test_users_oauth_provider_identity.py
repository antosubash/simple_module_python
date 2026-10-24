"""Per-provider email-verification proof for OAuth sign-in (GH #622)."""

import pytest
from users.oauth import OAuthProvider


class _Google:
    def __init__(self, verified):
        self.profile = {
            "resourceName": "people/1",
            "emailAddresses": [
                {"value": "other@example.com", "metadata": {"primary": False, "verified": True}},
                {"value": "me@example.com", "metadata": {"primary": True, "verified": verified}},
            ],
        }

    async def get_profile(self, token):
        return self.profile


class _GitHub:
    def __init__(self, emails, fail=False):
        self.emails, self.fail = emails, fail

    async def get_id_email(self, token):
        return "42", "me@example.com"

    async def get_emails(self, token):
        if self.fail:
            raise RuntimeError("scope missing")
        return self.emails


class _Microsoft:
    async def get_id_email(self, token):
        return "ms-1", "me@example.com"


@pytest.mark.parametrize("verified", [True, False, None])
async def test_google_uses_primary_email_verification(verified):
    provider = OAuthProvider("google", "Google", _Google(verified))
    assert await provider.get_identity("t") == ("people/1", "me@example.com", verified is True)


@pytest.mark.parametrize(
    "emails, expected",
    [
        ([{"email": "me@example.com", "verified": True, "primary": True}], True),
        ([{"email": "me@example.com", "verified": False, "primary": True}], False),
        ([{"email": "other@example.com", "verified": True}], False),
    ],
)
async def test_github_requires_the_chosen_email_to_be_verified(emails, expected):
    provider = OAuthProvider("github", "GitHub", _GitHub(emails))
    assert await provider.get_identity("t") == ("42", "me@example.com", expected)


async def test_github_unreadable_emails_is_not_proof():
    provider = OAuthProvider("github", "GitHub", _GitHub([], fail=True))
    assert (await provider.get_identity("t"))[2] is False


async def test_microsoft_email_is_never_proof():
    provider = OAuthProvider("microsoft", "Microsoft", _Microsoft())
    assert await provider.get_identity("t") == ("ms-1", "me@example.com", False)
