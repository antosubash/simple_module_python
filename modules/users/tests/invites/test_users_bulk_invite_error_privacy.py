"""Invite responses never expose database statements or exception details (#698)."""

import pytest
from fastapi_users.exceptions import UserAlreadyExists
from sqlalchemy.exc import IntegrityError
from users.invites.bulk import _failure_detail


@pytest.mark.parametrize(
    "error",
    [
        IntegrityError(
            "INSERT INTO users VALUES (:password)", {"password": "secret"}, Exception("db")
        ),
        RuntimeError("private backend details"),
        Exception(),
    ],
)
def test_users_bulk_invite_unknown_error_is_generic(error):
    assert _failure_detail(error) == "The invitation could not be created. Please try again."


def test_users_bulk_invite_already_exists_has_safe_message():
    assert _failure_detail(UserAlreadyExists()) == "Already a member of this workspace"
