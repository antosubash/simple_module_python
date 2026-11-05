"""A credential used as a primary key never reaches the entity-change log."""

import uuid

from simple_module_db.listeners import _entity_pk
from users.models import RefreshToken, User


def test_token_primary_key_is_masked_in_log_identity():
    token = RefreshToken(token="private", user_id=uuid.uuid4())
    assert _entity_pk(token) == "[redacted]"


def test_ordinary_primary_key_is_kept():
    user = User(email="log@test")
    assert _entity_pk(user) != "[redacted]"
