"""``user_state`` and its TypeScript twin must answer the same question.

``deriveState`` (``admin/components/user-list-item.ts``) reimplements
``user_state`` so the edit page can recompute the status pill after a local
change without a reload. Nothing pinned the two together, so the first edit to
either would have drifted them silently — a row rendered "disabled" by the
server and "unverified" by the client, or vice versa.

The table below is the shared truth. Its TypeScript half lives in
``modules/users/tests-js/deriveState.test.ts`` and reads the same four cases.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from users.admin.user_state import user_state
from users.contracts.schemas import USER_STATES

_INVITED_AT = datetime(2026, 9, 1, tzinfo=UTC)

# (is_active, is_verified, invited_at, expected)
CASES = [
    (True, True, None, "active"),
    (True, True, _INVITED_AT, "active"),
    (True, False, _INVITED_AT, "invited"),
    (True, False, None, "unverified"),
    (False, True, None, "disabled"),
    (False, False, _INVITED_AT, "disabled"),
]


@pytest.mark.parametrize("is_active,is_verified,invited_at,expected", CASES)
def test_every_combination_has_one_answer(
    is_active: bool, is_verified: bool, invited_at: datetime | None, expected: str
) -> None:
    assert user_state(is_active, is_verified, invited_at) == expected


def test_disabled_wins_over_everything_else() -> None:
    """Order matters: an inactive account is disabled whatever else is true."""
    assert user_state(False, True, _INVITED_AT) == "disabled"


def test_the_table_covers_every_declared_state() -> None:
    """A new state added to ``USER_STATES`` without a case here is a gap."""
    assert {case[-1] for case in CASES} == set(USER_STATES)
