"""Pin the shape of the Alembic revision graph (GH #503).

The history is *not* one linear chain: it has several roots and heads, and
``branch_labels`` are inherited by every descendant. Adding a root, a head or a
revision without updating the tables below fails this test on purpose, so the
change is made consciously and ``docs/database/migrations.md`` stays true.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

_HOST = Path(__file__).resolve().parents[1]

# Module that owns the tables each revision creates or alters. "core" marks
# revisions that touch several modules' tables at once.
_OWNER: dict[str, str] = {
    "77162e7b184b": "core",  # initial schema: background_tasks, feature_flags, file_storage, ...
    "3bf3f9db7f7f": "users",
    "41cf2c53660e": "users",
    "873ca2015033": "users",
    "92965b00f105": "users",
    "f53464f5ac43": "users",
    "b4c1e7d9a025": "users",
    "c3a1d7e45f20": "users",
    "d4e8a1b6c392": "users",
    "b5018b617142": "users",
    "c8e4f1a2b6d9": "users",
    "d7b3a9e5c1f2": "mail",  # data-only: users.* settings keys -> mail.*
    "a659221c464b": "file_storage",
    "e5a8c1f27b94": "file_storage",
    "c7f2d9a41e83": "file_storage",
    "e5f2a8c1d7b3": "core",  # timezone-aware timestamps across modules
    "b5d3f08a6e17": "background_tasks",
    "e878882924e7": "background_tasks",
    "51b2058d8afd": "api_tokens",
    "168a2882f443": "keycloak",
    "f6a3b9d2e8c4": "keycloak",
    "e36ab09c4a92": "tenants",
    "f1a9c3d7b2e4": "tenants",
    "70786227af4c": "audit_log",
    "a7c2e91d4b58": "audit_log",
    "f733c7938fd1": "sharing",
}

_ROOTS = {"77162e7b184b", "e36ab09c4a92", "f733c7938fd1"}

# head revision -> module owning the tables it creates or alters.
_HEADS = {
    "a7c2e91d4b58": "audit_log",
    "d7b3a9e5c1f2": "mail",  # reported as ``api_tokens`` (inherited label)
    "f1a9c3d7b2e4": "tenants",
    "f6a3b9d2e8c4": "keycloak",
    "f733c7938fd1": "sharing",
}

# Labels written in the revision files themselves.
_DECLARED_LABELS = {
    "70786227af4c": "audit_log",
    "51b2058d8afd": "api_tokens",
    "168a2882f443": "keycloak",
    "e36ab09c4a92": "tenants",
    "f733c7938fd1": "sharing",
}

# Known mislabels: revisions that inherit a label from an ancestor owned by a
# different module (the ``api_tokens`` label sits on the trunk). Existing
# revision files are not edited; see docs/database/migrations.md.
_INHERITED_MISLABELS = {
    "a659221c464b": "api_tokens",
    "e5a8c1f27b94": "api_tokens",
    "e5f2a8c1d7b3": "api_tokens",
    "c7f2d9a41e83": "api_tokens",
    "b5d3f08a6e17": "api_tokens",
    "e878882924e7": "api_tokens",
    "d4e8a1b6c392": "api_tokens",
    "c3a1d7e45f20": "api_tokens",
    "b4c1e7d9a025": "api_tokens",
    "f53464f5ac43": "api_tokens",
    "92965b00f105": "api_tokens",
    "b5018b617142": "api_tokens",
    "c8e4f1a2b6d9": "api_tokens",
    "d7b3a9e5c1f2": "api_tokens",
}


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(_HOST / "alembic.ini")))


def test_every_revision_has_a_known_owner(script: ScriptDirectory) -> None:
    revisions = {r.revision for r in script.walk_revisions()}
    assert revisions == set(_OWNER), (
        "revision set changed; add new revisions to _OWNER "
        f"(new: {sorted(revisions - set(_OWNER))}, gone: {sorted(set(_OWNER) - revisions)})"
    )


def test_roots(script: ScriptDirectory) -> None:
    assert set(script.get_bases()) == _ROOTS


def test_heads_and_their_owners(script: ScriptDirectory) -> None:
    heads = set(script.get_heads())
    assert heads == set(_HEADS), f"heads changed: {sorted(heads)}"
    for head, module in _HEADS.items():
        assert _OWNER[head] == module


def test_declared_labels_match_owning_module(script: ScriptDirectory) -> None:
    declared = {
        r.revision: next(iter(labels))
        for r in script.walk_revisions()
        if (labels := getattr(r.module, "branch_labels", None))
    }
    assert declared == _DECLARED_LABELS
    for rev, label in declared.items():
        assert _OWNER[rev] == label, f"{rev} is labelled {label!r} but owned by {_OWNER[rev]!r}"


def test_inherited_labels_are_the_known_mislabels(script: ScriptDirectory) -> None:
    mislabels = {}
    for r in script.walk_revisions():
        effective = sorted(r.branch_labels)
        if effective and effective != [_OWNER[r.revision]]:
            mislabels[r.revision] = effective[0]
    assert mislabels == _INHERITED_MISLABELS
