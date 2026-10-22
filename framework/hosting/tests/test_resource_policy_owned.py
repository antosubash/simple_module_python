"""OwnedResourcePolicy: owner / public / shared / bypass, lists and counts in SQL (GH #526)."""

from __future__ import annotations

import pytest
from _resacc_models import (
    BYPASS,
    EDITOR,
    OWNER,
    POLICY,
    SHARED,
    STRANGER,
    ResaccDoc,
    principal,
    seed,
)
from simple_module_core.resources import (
    ACTION_EDIT,
    ACTION_VIEW,
    ResourceType,
    ResourceTypeError,
    ResourceTypeRegistry,
)
from simple_module_db import PageParams, paginate
from simple_module_db.resource_policy import OwnedResourcePolicy, load_authorized, select_by_id
from sqlmodel import select


@pytest.fixture
async def docs(db_session):
    return await seed(db_session)


async def _titles(session, who, action=ACTION_VIEW) -> list[str]:
    stmt = POLICY.filter(who, action, select(ResaccDoc).order_by(ResaccDoc.title))
    return [d.title for d in (await session.execute(stmt)).scalars()]


async def test_owner_sees_own_and_public(db_session, docs):
    assert await _titles(db_session, principal(OWNER)) == ["private", "public"]


async def test_stranger_sees_only_public_and_own(db_session, docs):
    assert await _titles(db_session, principal(STRANGER)) == ["other", "public"]


async def test_shared_user_sees_shared_row(db_session, docs):
    assert await _titles(db_session, principal(SHARED)) == ["private", "public"]


async def test_public_is_view_only(db_session, docs):
    assert await _titles(db_session, principal(SHARED), ACTION_EDIT) == []
    assert await _titles(db_session, principal(EDITOR), ACTION_EDIT) == ["private"]


async def test_anonymous_sees_public_only(db_session, docs):
    assert await _titles(db_session, principal(None)) == ["public"]


async def test_bypass_permission_and_wildcard_see_everything(db_session, docs):
    assert len(await _titles(db_session, principal(STRANGER, BYPASS))) == 3
    assert len(await _titles(db_session, principal(STRANGER, "*"))) == 3


async def test_no_bypass_means_even_wildcard_is_filtered(db_session, docs):
    strict = OwnedResourcePolicy(ResaccDoc.owner_id, bypass_perm=None)
    stmt = strict.filter(principal(STRANGER, "*"), ACTION_VIEW, select(ResaccDoc))
    assert [d.title for d in (await db_session.execute(stmt)).scalars()] == ["other"]


async def test_paginate_count_matches_filtered_list(db_session, docs):
    stmt = POLICY.filter(principal(STRANGER), ACTION_VIEW, select(ResaccDoc).order_by("title"))
    page = await paginate(db_session, stmt, PageParams(per_page=1))
    assert page.total == 2
    assert page.pages == 2


async def test_can_fast_path(docs):
    doc = docs["private"]
    assert POLICY.can(principal(OWNER), ACTION_EDIT, doc)
    assert not POLICY.can(principal(STRANGER), ACTION_VIEW, doc)
    assert POLICY.can(principal(STRANGER), ACTION_VIEW, docs["public"])
    assert not POLICY.can(principal(STRANGER), ACTION_EDIT, docs["public"])
    assert POLICY.can(principal(STRANGER, BYPASS), ACTION_EDIT, doc)


async def test_load_authorized_404_403_and_share_role(db_session, docs):
    by_id = select_by_id(ResaccDoc)
    stmt = by_id(str(docs["private"].id))
    assert await load_authorized(db_session, POLICY, principal(STRANGER), ACTION_VIEW, stmt) == (
        None,
        False,
    )
    row, allowed = await load_authorized(db_session, POLICY, principal(SHARED), ACTION_EDIT, stmt)
    assert row is not None and not allowed
    row, allowed = await load_authorized(db_session, POLICY, principal(EDITOR), ACTION_EDIT, stmt)
    assert row is not None and allowed


def test_select_by_id_rejects_malformed_ids():
    with pytest.raises(ValueError):
        select_by_id(ResaccDoc)("not-a-uuid")


def test_registry_validates_names_and_duplicates():
    registry = ResourceTypeRegistry()
    rt = ResourceType(name="resacc.doc", policy=POLICY, select_by_id=select_by_id(ResaccDoc))
    registry.register(rt)
    assert registry.get("resacc.doc") is rt and "resacc.doc" in registry
    with pytest.raises(ResourceTypeError):
        registry.register(rt)
    with pytest.raises(ResourceTypeError):
        registry.register(ResourceType(name="Bad", policy=POLICY, select_by_id=rt.select_by_id))
