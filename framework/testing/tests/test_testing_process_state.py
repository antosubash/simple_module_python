"""Process services are isolated between plugin-built apps and tests."""

from unittest.mock import Mock

from simple_module_core.leases import (
    InProcessLeaseBackend,
    configure_leases,
    get_leases,
    reset_lease_backend,
)
from simple_module_core.mail import (
    ConsoleMailSender,
    current_mail_sender,
    install_mail_resolver,
    install_mail_sender,
    mail_transport_installed,
    reset_mail_sender,
    resolve_mail_sender,
)
from simple_module_hosting import sentry
from simple_module_test.mail import CapturedMail
from simple_module_test.process_state import reset_process_state


async def test_reset_mail_clears_sender_and_worker_resolver() -> None:
    sender = CapturedMail()

    async def resolver(db):
        return sender

    install_mail_sender(sender)
    install_mail_resolver(resolver)
    reset_mail_sender()
    assert not mail_transport_installed()
    assert isinstance(current_mail_sender(), ConsoleMailSender)
    assert isinstance(await resolve_mail_sender(object()), ConsoleMailSender)
    assert current_mail_sender().include_body is False


async def test_reset_leases_discards_configuration_and_held_names() -> None:
    original = InProcessLeaseBackend()
    configure_leases(original)
    assert await original.acquire("held", "previous-app", 60) == 1
    reset_lease_backend()
    replacement = get_leases()
    assert replacement is not original
    assert isinstance(replacement, InProcessLeaseBackend)
    assert await replacement.acquire("held", "next-app", 60) == 1


def test_reset_sentry_closes_and_unbinds_client(monkeypatch) -> None:
    import pytest

    sdk = pytest.importorskip("sentry_sdk")
    scope = Mock()
    monkeypatch.setattr(sdk, "get_global_scope", lambda: scope)
    monkeypatch.setattr(sentry, "_enabled", True)
    sentry._request_scope.set({"type": "http"})
    sentry.reset_sentry()
    scope.client.close.assert_called_once_with()
    scope.set_client.assert_called_once_with(None)
    assert not sentry.is_enabled()
    assert sentry._request_scope.get() is None
    sentry.reset_sentry()
    scope.client.close.assert_called_once_with()


async def test_plugin_second_app_keeps_first_apps_services(settings, monkeypatch) -> None:
    """Resets are per test (autouse fixture), so a second app in one test must not
    wipe the first app's installed mail sender."""
    from fastapi import FastAPI
    from simple_module_hosting import app_builder
    from simple_module_test import fixtures

    def create_app(settings):
        app = FastAPI()
        app.state.sm = Mock()
        return app

    async def create_tables(engine):
        pass

    monkeypatch.setattr(app_builder, "create_app", create_app)
    monkeypatch.setattr(fixtures, "_create_all_tables", create_tables)
    install_mail_sender(CapturedMail())
    async for _app in fixtures._build_app(settings, seed_admin=False):
        assert mail_transport_installed()
    reset_process_state()


def test_autouse_reset_clears_state_left_by_a_previous_test() -> None:
    # The autouse ``_reset_process_state`` fixture ran before this test.
    assert not mail_transport_installed()
    assert not sentry.is_enabled()
