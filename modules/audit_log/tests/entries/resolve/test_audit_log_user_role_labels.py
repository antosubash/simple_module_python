"""Role-assignment history names both sides without exposing the user directory."""

import uuid

import pytest
from audit_log.entries.resolve import entity_link, resolve_entity_labels
from simple_module_core.web.audit_links import AuditLinkRegistry
from simple_module_db.auditing.audit import format_pk
from users.core.constants import Permissions
from users.models import Role, User, UserRole
from users.module import UsersModule


@pytest.fixture
def registry():
    links = AuditLinkRegistry()
    UsersModule().register_audit_links(links)
    return links


def test_role_assignments_register_a_label_resolver(registry):
    assert registry.get("UserRole").label_resolver is not None


async def test_role_assignment_history_names_removed_assignments(db_session, registry):
    user = User(email="sam@example.com", hashed_password="x", full_name="Sam")
    roles = [Role(name="editor"), Role(name="reviewer")]
    db_session.add_all([user, *roles])
    await db_session.flush()
    assignments = [UserRole(user_id=user.id, role_id=role.id) for role in roles]
    db_session.add_all(assignments)
    await db_session.flush()
    refs = [("UserRole", format_pk((user.id, role.id))) for role in roles]
    for assignment in assignments:
        await db_session.delete(assignment)
    await db_session.flush()

    labels = await resolve_entity_labels(db_session, registry, refs, {Permissions.MANAGE})

    assert labels == {refs[0]: "editor · sam@example.com", refs[1]: "reviewer · sam@example.com"}
    entity = entity_link(registry, *refs[0], display=labels[refs[0]])
    assert entity["display"] == "editor · sam@example.com"
    assert entity["table_name"] == "users_user_role"
    assert entity["url"] is None


async def test_role_assignment_labels_require_users_manage(db_session, registry):
    user = User(email="private@example.com", hashed_password="x")
    role = Role(name="editor")
    db_session.add_all([user, role])
    await db_session.flush()
    ref = ("UserRole", format_pk((user.id, role.id)))

    assert await resolve_entity_labels(db_session, registry, [ref], {"audit_log.view"}) == {}
    assert await resolve_entity_labels(db_session, registry, [ref], {"*"}) == {
        ref: "editor · private@example.com"
    }


async def test_unknown_or_malformed_role_assignment_ids_fall_back(db_session, registry):
    refs = [
        ("UserRole", raw)
        for raw in [
            "bad",
            "(UUID('bad'), UUID('bad'))",
            format_pk((uuid.uuid4(), uuid.uuid4())),
            format_pk((uuid.uuid4(), uuid.uuid4(), uuid.uuid4())),
        ]
    ]

    assert await resolve_entity_labels(db_session, registry, refs, {Permissions.MANAGE}) == {}
