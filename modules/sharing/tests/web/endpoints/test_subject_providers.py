"""Typed subject grants, discovery, labels and live role access over HTTP (#963)."""

import uuid

import pytest
from _sharing_support import (
    NOTE_POLICY,
    NOTE_TYPE,
    SharingTestNote,
    create_note_table,
    register_note_type,
)
from fastapi import Depends
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_core.access.tenancy import TenantRole
from simple_module_hosting.auth.resource_deps import resource_principal
from sqlmodel import select

PATH = "/api/sharing"


@pytest.fixture
def settings(settings):
    settings.i18n_supported_locales = ["en", "de"]
    return settings


@pytest.fixture
async def subjects_app(app):
    register_note_type(app.state.sm.resource_types)
    async with app.state.sm.db.engine.begin() as conn:
        await create_note_table(conn)

    @app.get("/subject-test/notes")
    async def notes(who: ResourcePrincipal = Depends(resource_principal)):
        async with app.state.sm.db.session_factory() as db:
            stmt = NOTE_POLICY.filter(who, "view", select(SharingTestNote))
            return [str(n.id) for n in (await db.execute(stmt)).scalars()]

    return app


async def seed(app, owner):
    async with app.state.sm.db.session_factory() as db:
        note = SharingTestNote(owner_id=uuid.UUID(owner))
        db.add(note)
        await db.commit()
        return {"resource_type": NOTE_TYPE, "resource_id": str(note.id)}


async def test_role_candidates_match_request_locale_labels(subjects_app, tenant_client):
    async with tenant_client(TenantRole.OWNER) as owner:
        resource = await seed(subjects_app, owner.user_id)
        for locale, query, expected in (
            ("en", "Members", ["member"]),
            ("en", "Owners", ["owner"]),
            ("en", "Administrators", ["admin"]),
            ("de", "Mitglieder", ["member"]),
            ("de", "Eigentümer", ["owner"]),
            ("de", "Administratoren", ["admin"]),
            ("en", "Mitglieder", []),
            ("de", "Owners", []),
        ):
            response = await owner.client.get(
                f"{PATH}/candidates",
                params={**resource, "subject_type": "tenant_role", "q": query},
                headers={"Accept-Language": locale},
            )
            assert response.status_code == 200, response.text
            assert [candidate["id"] for candidate in response.json()] == expected


async def test_role_grant_candidates_labels_and_access(subjects_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as member,
        tenant_client(TenantRole.ADMIN, tenant_id=owner.tenant_id) as admin,
        tenant_client(TenantRole.MEMBER) as foreign,
    ):
        resource = await seed(subjects_app, owner.user_id)
        types = await owner.client.get(f"{PATH}/subject-types", params=resource)
        assert types.status_code == 200
        assert {t["subject_type"] for t in types.json()} == {"user", "tenant_role"}
        assert (
            await member.client.get(f"{PATH}/subject-types", params=resource)
        ).status_code == 404
        candidates = await owner.client.get(
            f"{PATH}/candidates", params={**resource, "subject_type": "tenant_role", "q": "member"}
        )
        assert candidates.status_code == 200
        assert candidates.json() == [
            {
                "id": "member",
                "subject_type": "tenant_role",
                "display_name": "tenant:member",
                "email": "",
            }
        ]
        response = await owner.client.post(
            f"{PATH}/shares",
            json={**resource, "subject_type": "tenant_role", "subject_id": "member"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["subject_label"] == "tenant:member"
        assert resource["resource_id"] in (await member.client.get("/subject-test/notes")).json()
        for other in (admin, foreign):
            assert (
                resource["resource_id"]
                not in (await other.client.get("/subject-test/notes")).json()
            )
        changed = await owner.client.patch(
            f"/api/tenants/current/members/{member.user_id}", json={"role": "admin"}
        )
        assert changed.status_code == 200, changed.text
        assert (
            resource["resource_id"] not in (await member.client.get("/subject-test/notes")).json()
        )


async def test_unknown_and_invalid_role_refused(subjects_app, tenant_client):
    async with tenant_client() as owner:
        resource = await seed(subjects_app, owner.user_id)
        for subject_type, subject_id in (("unregistered", "one"), ("tenant_role", "typo")):
            response = await owner.client.post(
                f"{PATH}/shares",
                json={**resource, "subject_type": subject_type, "subject_id": subject_id},
            )
            assert response.status_code == 422
        response = await owner.client.get(
            f"{PATH}/candidates", params={**resource, "subject_type": "unknown", "q": ""}
        )
        assert response.status_code == 422


async def test_module_registered_subject_routes_validation_labels_and_membership(
    subjects_app, tenant_client
):
    from unittest.mock import AsyncMock

    from sharing.contracts import ShareCandidate, SubjectProvider, get_subject_registry
    from sqlalchemy import false

    async with tenant_client() as owner, tenant_client(tenant_id=owner.tenant_id) as friend:
        resource = await seed(subjects_app, owner.user_id)
        validate = AsyncMock(return_value="one")
        labels = AsyncMock(return_value={"one": "Team One"})
        candidates = AsyncMock(return_value=[ShareCandidate(id="one", display_name="Team One")])
        subjects = get_subject_registry(subjects_app)
        subjects.register(
            SubjectProvider(
                name="team",
                label_key="teams.share_type",
                validate=validate,
                labels=labels,
                candidates=candidates,
                membership=lambda who, subject_id: (
                    subject_id.in_(["one"]) if who.user_id == friend.user_id else false()
                ),
            )
        )
        found = await owner.client.get(
            f"{PATH}/candidates", params={**resource, "q": "one", "subject_type": "team"}
        )
        assert found.status_code == 200
        assert found.json()[0]["subject_type"] == "team"
        response = await owner.client.post(
            f"{PATH}/shares", json={**resource, "subject_type": "team", "subject_id": "one"}
        )
        assert response.status_code == 201, response.text
        assert response.json()["subject_label"] == "Team One"
        validate.assert_awaited_once()
        ctx, subject_id = validate.await_args.args
        assert subject_id == "one" and ctx.principal.tenant_id == owner.tenant_id
        labels.assert_awaited_once()
        assert resource["resource_id"] in (await friend.client.get("/subject-test/notes")).json()
        validate.return_value = None
        rejected = await owner.client.post(
            f"{PATH}/shares", json={**resource, "subject_type": "team", "subject_id": "hidden"}
        )
        assert rejected.status_code == 422
