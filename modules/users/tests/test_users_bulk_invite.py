"""Bulk invite — many addresses per submit, with per-address outcomes.

The invite form took one address at a time, so onboarding a team meant
repeating the form once per person. Partial success is the normal case here:
one already-registered address must not discard the rest.
"""

from __future__ import annotations

import httpx
import pytest

_URL = "/api/users/admin/invite/bulk"


class TestBulkInvite:
    async def test_invites_every_address(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            _URL,
            json={"emails": ["a@example.com", "b@example.com"], "role_names": []},
        )
        assert resp.status_code == 200, resp.text
        results = resp.json()["results"]
        assert [r["email"] for r in results] == ["a@example.com", "b@example.com"]

    async def test_duplicate_addresses_are_invited_once(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Pasting a list with a repeat should not mint two invites for it."""
        resp = await authenticated_client.post(
            _URL,
            json={"emails": ["dup@example.com", "DUP@example.com"], "role_names": []},
        )
        assert len(resp.json()["results"]) == 1

    async def test_addresses_are_normalised_to_lowercase(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.post(
            _URL, json={"emails": ["Mixed@Example.com"], "role_names": []}
        )
        assert resp.json()["results"][0]["email"] == "mixed@example.com"

    async def test_one_failure_does_not_discard_the_others(
        self, authenticated_client: httpx.AsyncClient
    ):
        """A duplicate in a pasted list of twenty must not lose the other 19."""
        await authenticated_client.post(
            _URL, json={"emails": ["taken@example.com"], "role_names": []}
        )
        resp = await authenticated_client.post(
            _URL,
            json={"emails": ["taken@example.com", "fresh@example.com"], "role_names": []},
        )
        assert resp.status_code == 200, resp.text
        by_email = {r["email"]: r for r in resp.json()["results"]}
        assert by_email["taken@example.com"]["status"] == "failed"
        assert by_email["fresh@example.com"]["status"] in ("sent", "link")

    async def test_a_failure_always_carries_a_reason(self, authenticated_client: httpx.AsyncClient):
        """Every failed row must say why.

        ``str(UserAlreadyExists())`` is empty — the reason lives in the type, not
        the message — so passing it through rendered an address in red with a
        blank reason beside it. Asserting the status alone is what let that ship.
        """
        await authenticated_client.post(
            _URL, json={"emails": ["why@example.com"], "role_names": []}
        )
        resp = await authenticated_client.post(
            _URL, json={"emails": ["why@example.com"], "role_names": []}
        )
        result = resp.json()["results"][0]
        assert result["status"] == "failed"
        assert result["detail"], "a failed address must explain itself"
        assert "already" in result["detail"].lower()

    async def test_console_mailer_hands_back_a_copyable_link(
        self, authenticated_client: httpx.AsyncClient
    ):
        """The test app uses the console mailer, which delivers nothing — the
        admin needs the link or the invite is undeliverable."""
        resp = await authenticated_client.post(
            _URL, json={"emails": ["linkme@example.com"], "role_names": []}
        )
        result = resp.json()["results"][0]
        assert result["status"] == "link"
        assert "/users/invite/accept?token=" in result["link"]

    async def test_roles_apply_to_every_address(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            _URL,
            json={"emails": ["r1@example.com", "r2@example.com"], "role_names": ["user"]},
        )
        assert resp.status_code == 200, resp.text
        assert all(r["status"] in ("sent", "link") for r in resp.json()["results"])

    async def test_roles_survive_a_later_failure(self, authenticated_client: httpx.AsyncClient):
        """A failure mid-list must not roll back an earlier invite's roles.

        ``invite`` only flushes its role rows; the rollback that clears failed
        transaction state used to take them with it, so the person invited just
        before a duplicate address ended up with none of the chosen roles.
        """
        await authenticated_client.post(
            _URL, json={"emails": ["dupe@example.com"], "role_names": []}
        )
        resp = await authenticated_client.post(
            _URL,
            json={"emails": ["kept@example.com", "dupe@example.com"], "role_names": ["admin"]},
        )
        assert resp.status_code == 200, resp.text

        listing = await authenticated_client.get("/api/users/admin")
        users = {u["email"]: u for u in listing.json()}
        assert users["kept@example.com"]["roles"] == ["admin"]

    async def test_a_malformed_address_does_not_reject_the_submit(
        self, authenticated_client: httpx.AsyncClient
    ):
        """A typo in one line of a pasted column used to 422 the whole body,
        leaving the admin with a generic error and no idea which line."""
        resp = await authenticated_client.post(
            _URL,
            json={"emails": ["good@example.com", "not-an-address"], "role_names": []},
        )
        assert resp.status_code == 200, resp.text
        by_email = {r["email"]: r for r in resp.json()["results"]}
        assert by_email["good@example.com"]["status"] in ("sent", "link")
        assert by_email["not-an-address"]["status"] == "failed"
        assert "valid email" in by_email["not-an-address"]["detail"]

    async def test_empty_list_is_accepted_and_does_nothing(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.post(_URL, json={"emails": [], "role_names": []})
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    async def test_address_count_is_capped(self, authenticated_client: httpx.AsyncClient):
        """One submit must not be able to mint unbounded live invite tokens."""
        from users.admin.bulk_invite import MAX_ADDRESSES

        emails = [f"bulk{i}@example.com" for i in range(MAX_ADDRESSES + 5)]
        resp = await authenticated_client.post(_URL, json={"emails": emails, "role_names": []})
        invited = [r for r in resp.json()["results"] if r["status"] != "failed"]
        assert len(invited) == MAX_ADDRESSES

    async def test_addresses_over_the_cap_are_reported_not_dropped(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Silent truncation reports "100 invites sent" while 5 people are
        never contacted, with nothing on screen saying so."""
        from users.admin.bulk_invite import MAX_ADDRESSES

        emails = [f"over{i}@example.com" for i in range(MAX_ADDRESSES + 5)]
        resp = await authenticated_client.post(_URL, json={"emails": emails, "role_names": []})
        results = resp.json()["results"]

        assert len(results) == MAX_ADDRESSES + 5, "every submitted address needs an outcome"
        overflow = {r["email"]: r for r in results[-5:]}
        assert set(overflow) == {
            f"over{i}@example.com" for i in range(MAX_ADDRESSES, MAX_ADDRESSES + 5)
        }
        for result in overflow.values():
            assert result["status"] == "failed"
            assert "limit" in result["detail"]

    async def test_requires_authentication(self, client: httpx.AsyncClient):
        resp = await client.post(
            _URL, json={"emails": ["x@example.com"], "role_names": []}, follow_redirects=False
        )
        assert resp.status_code in (302, 401, 403)


class TestInvitePreview:
    async def test_accept_page_names_the_invitee(
        self, authenticated_client: httpx.AsyncClient, client: httpx.AsyncClient
    ):
        """The card asked for a password while identifying nobody."""
        created = await authenticated_client.post(
            _URL, json={"emails": ["preview@example.com"], "role_names": []}
        )
        link = created.json()["results"][0]["link"]
        token = link.split("token=")[1]

        resp = await client.get(
            f"/users/invite/accept?token={token}",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        invite = resp.json()["props"]["invite"]
        assert invite["email"] == "preview@example.com"
        assert invite["already_accepted"] is False

    @pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
    async def test_unreadable_tokens_yield_no_preview(self, client: httpx.AsyncClient, token: str):
        """Expired, tampered and absent all look the same here on purpose —
        the reason belongs to the accept attempt, which validates properly."""
        resp = await client.get(
            f"/users/invite/accept?token={token}",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["props"]["invite"] is None

    async def test_preview_does_not_consume_the_invite(
        self, authenticated_client: httpx.AsyncClient, client: httpx.AsyncClient
    ):
        """Viewing the page must leave the token usable — UserManager.verify
        marks the account verified as a side effect, so the preview cannot
        route through it."""
        created = await authenticated_client.post(
            _URL, json={"emails": ["unspent@example.com"], "role_names": []}
        )
        token = created.json()["results"][0]["link"].split("token=")[1]

        for _ in range(2):
            resp = await client.get(
                f"/users/invite/accept?token={token}",
                headers={"X-Inertia": "true", "Accept": "application/json"},
            )
            assert resp.json()["props"]["invite"]["already_accepted"] is False

        accepted = await client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "a-good-password-123"},
        )
        assert accepted.status_code in (200, 204), accepted.text
