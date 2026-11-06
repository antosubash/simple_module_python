"""Self-service updates cannot carry account administration fields (#640)."""

import pytest
from users.contracts.schemas import UserUpdate


@pytest.mark.parametrize("field", ["is_superuser", "is_active", "is_verified"])
def test_user_update_drops_privileged_fields(field):
    update = UserUpdate.model_validate({field: True, "full_name": "Alice"})
    assert update.model_dump(exclude_unset=True) == {"full_name": "Alice"}
    assert field not in UserUpdate.model_json_schema()["properties"]
