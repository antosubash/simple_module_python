"""Reset process services between tests and apps built by the test plugin."""

from collections.abc import Iterator

import pytest
from simple_module_core.leases import reset_lease_backend
from simple_module_core.mail import reset_mail_sender
from simple_module_core.settings_hydrate import env_supplied_fields
from simple_module_hosting._api_version import default_api_version
from simple_module_hosting.sentry import reset_sentry


def reset_process_state() -> None:
    """Restore unconfigured services without retaining another app's resources."""
    reset_mail_sender()
    reset_lease_backend()
    reset_sentry()
    env_supplied_fields.cache_clear()
    default_api_version.cache_clear()


@pytest.fixture(autouse=True)
def _reset_process_state() -> Iterator[None]:
    reset_process_state()
    try:
        yield
    finally:
        reset_process_state()
