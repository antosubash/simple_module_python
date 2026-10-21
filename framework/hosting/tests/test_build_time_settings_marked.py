"""Every HostSettings field ``create_app`` consumes is marked ``requires_restart``.

The module list, the i18n registry, the DB engine and the middleware stack are
all built from settings before the lifespan exists, so an admin-UI edit to one
of those fields changes nothing until the process restarts (#499). The marker
is what makes the settings editor say so.

Rather than a hand-kept list, this builds the app on a ``Settings`` that
records every field read during ``create_app`` — so a new build-time read
without the marker fails here. It runs twice, because some reads sit behind a
branch (``default_tenant`` only matters when ``multi_tenant`` is off). And the
reverse direction: a marked field that nothing reads at build time is a stale
marker that tells operators to restart for no reason.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.settings import Settings

# Consumed at build time outside create_app: host/main.py hands them to
# setup_logging once, before create_app runs.
_READ_BY_HOST_ENTRYPOINT = frozenset({"log_level", "log_format"})

# Declared by hosting batch 1 groundwork (S0) before the feature slices that read
# them in create_app. Each slice deletes its own fields from this set.
_NOT_YET_CONSUMED = frozenset(
    {
        "forwarded_host_allowlist",
        "cors_allow_origins",
        "cors_allow_credentials",
        "cors_allow_methods",
        "cors_allow_headers",
        "cors_expose_headers",
        "cors_max_age",
    }
)


class _RecordingSettings(Settings):
    reads: ClassVar[set[str]] = set()

    def __getattribute__(self, name: str) -> Any:
        if name in HostSettings.model_fields:
            _RecordingSettings.reads.add(name)
        return super().__getattribute__(name)


def _build_reads(base: Settings, **changes: Any) -> set[str]:
    data = base.model_dump() | changes
    recording = _RecordingSettings.model_construct(**data)
    _RecordingSettings.reads = set()
    create_app(recording)  # build only — the lifespan never starts
    return set(_RecordingSettings.reads)


def _marked() -> set[str]:
    out = set()
    for name, info in HostSettings.model_fields.items():
        extra = info.json_schema_extra
        if isinstance(extra, dict) and extra.get("requires_restart") is True:
            out.add(name)
    return out


@pytest.fixture
def build_time_fields(settings: Settings) -> set[str]:
    reads = _build_reads(settings)
    reads |= _build_reads(settings, multi_tenant=False, default_tenant="acme")
    return reads | _READ_BY_HOST_ENTRYPOINT


def test_every_build_time_field_is_marked(build_time_fields: set[str]) -> None:
    missing = sorted(build_time_fields - _marked())
    assert not missing, f"read by create_app but not marked requires_restart: {missing}"


def test_every_marked_field_is_read_at_build_time(build_time_fields: set[str]) -> None:
    stale = sorted(_marked() - build_time_fields - _NOT_YET_CONSUMED)
    assert not stale, f"marked requires_restart but create_app never reads them: {stale}"


def test_runtime_fields_stay_unmarked() -> None:
    """Maintenance mode flips live — that is the point of storing it in the DB."""
    assert not ({"maintenance_mode", "maintenance_message"} & _marked())
