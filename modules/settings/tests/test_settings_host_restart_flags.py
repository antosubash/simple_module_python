"""The settings editor receives the restart marker on build-time host fields (#499)."""

from __future__ import annotations

import pytest
from settings._module_settings import _build_view
from simple_module_hosting.host_settings import HostSettings


@pytest.mark.parametrize(
    "field",
    ["multi_tenant", "tenant_header", "i18n_default_locale", "auth_provider", "log_format"],
)
def test_host_view_flags_build_time_field(field: str) -> None:
    view = _build_view("Host", "host", HostSettings())
    by_name = {f.name: f for f in view.fields}
    assert by_name[field].requires_restart is True


def test_host_view_leaves_runtime_field_unflagged() -> None:
    view = _build_view("Host", "host", HostSettings())
    assert {f.name: f for f in view.fields}["maintenance_mode"].requires_restart is False
