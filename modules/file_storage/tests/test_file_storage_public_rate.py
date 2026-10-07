"""Public file GETs get their own rate-limit bucket, wider than the default."""

from __future__ import annotations

from file_storage import constants


async def test_file_storage_public_route_has_its_own_rate(app) -> None:
    file_id = "00000000-0000-0000-0000-000000000000"
    path = f"{constants.ROUTE_PREFIX_API}{constants.PUBLIC_SEGMENT}/{file_id}"
    rule = app.state.public_routes.match("GET", path)
    assert rule is not None
    assert rule.rate == constants.PUBLIC_FILES_RATE
