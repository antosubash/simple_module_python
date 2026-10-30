"""Once exclusions use the announced cache key (#694)."""

import pytest
from simple_module_inertia.props import once
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props


@pytest.mark.parametrize("partial", [False, True])
async def test_custom_once_key_exclusion_skips_loader_and_value(partial):
    def fail_if_called():
        pytest.fail("Excluded once loader must not run")

    headers = {"X-Inertia": "true", "X-Inertia-Except-Once-Props": "feature-flags"}
    if partial:
        headers.update({"X-Inertia-Partial-Component": "Page", "X-Inertia-Partial-Data": "flags"})
    out = await resolve_props(
        {"flags": once(fail_if_called, key="feature-flags")},
        {},
        "Page",
        InertiaRequest.from_headers(headers, method="GET"),
    )
    assert out.props == {}
    assert out.once == {}


async def test_custom_once_key_does_not_exclude_by_prop_name():
    out = await resolve_props(
        {"flags": once(lambda: ["enabled"], key="feature-flags")},
        {},
        "Page",
        InertiaRequest.from_headers({"X-Inertia-Except-Once-Props": "flags"}, method="GET"),
    )
    assert out.props == {"flags": ["enabled"]}
    assert out.once == {"feature-flags": {"prop": "flags", "expiresAt": None}}
