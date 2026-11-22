"""Registered transports survive startup, worker resolution and settings reloads."""

from types import SimpleNamespace

import pytest
from mail.core.settings import MailSettings
from mail.delivery.runtime import install_app_sender, resolve_sender_from_db
from mail.delivery.sender import build_sender
from mail.module import MailModule
from pydantic import ValidationError
from settings.core.service import SettingService
from settings.module_settings.discovery import collect_module_settings
from settings.module_settings.reload import apply_changes_and_reload
from settings.module_settings.store import SettingsStore
from simple_module_core.eventing.events import EventBus
from simple_module_core.mailer import mail as core_mail
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.settings.settings_base import DbBackedSettings
from simple_module_db.engine.transaction import finalize_session
from simple_module_test.mail import CapturedMail


class ProviderSettings(DbBackedSettings):
    from_address: str = "default@example.com"


class ProviderSender(CapturedMail):
    def __init__(self, options, log_bodies):
        super().__init__()
        self.from_address = options.from_address


@pytest.fixture
def provider(monkeypatch):
    from mail.contracts import register_mail_transport
    from mail.core import transports

    monkeypatch.setattr(transports, "_transports", dict(transports._transports))
    previous_names = list(transports.TRANSPORT_NAMES)
    register_mail_transport(
        "http-api", ProviderSender, settings_model=ProviderSettings, package="provider"
    )
    yield
    transports.TRANSPORT_NAMES[:] = previous_names


def test_custom_transport_can_be_selected(provider):
    sender = build_sender(
        MailSettings(backend="http-api"), options=ProviderSettings(from_address="api@test")
    )
    assert isinstance(sender, ProviderSender)
    assert sender.from_address == "api@test"


def test_repeated_registration_is_safe_but_conflicts_fail(provider):
    from mail.contracts import register_mail_transport

    register_mail_transport(
        "http-api", ProviderSender, settings_model=ProviderSettings, package="provider"
    )
    for name in ("http-api", "console", "smtp"):
        with pytest.raises(ValueError, match="already registered"):
            register_mail_transport(name, lambda options, log_bodies: CapturedMail())


def test_provider_settings_require_a_package(provider):
    from mail.contracts import register_mail_transport

    with pytest.raises(ValueError, match="supplied together"):
        register_mail_transport("invalid", ProviderSender, settings_model=ProviderSettings)


def test_unknown_transport_fails_in_production_and_logs_in_development(caplog):
    settings = MailSettings(backend="uninstalled")
    with pytest.raises(ValueError, match=r"Unknown mail transport.*uninstalled"):
        build_sender(settings, development=False)
    assert isinstance(build_sender(settings), core_mail.ConsoleMailSender)
    assert "uninstalled" in caplog.text


async def test_explicit_sender_survives_startup_and_reload(app):
    explicit = CapturedMail()
    core_mail.install_mail_sender(explicit)
    install_app_sender(app)
    async with app.state.sm.db.session_factory() as db:
        await apply_changes_and_reload(
            app,
            app.state.sm.event_bus,
            SettingsStore(SettingService(db)),
            package="mail",
            changes={"backend": "smtp"},
        )
        await finalize_session(db)
    assert core_mail.current_mail_sender() is explicit
    assert await core_mail.resolve_mail_sender(object()) is explicit


async def test_registered_transport_reload_and_admin_choices(app, provider):
    register_module_settings(
        app, "provider", ProviderSettings, lambda s: SimpleNamespace(settings=s)
    )
    async with app.state.sm.db.session_factory() as db:
        store = SettingsStore(SettingService(db))
        await apply_changes_and_reload(
            app,
            app.state.sm.event_bus,
            store,
            package="provider",
            changes={"from_address": "first@test"},
        )
        await finalize_session(db)
        await apply_changes_and_reload(
            app,
            app.state.sm.event_bus,
            store,
            package="mail",
            changes={"backend": "http-api"},
        )
        await finalize_session(db)
        assert core_mail.current_mail_sender().from_address == "first@test"
        await apply_changes_and_reload(
            app,
            app.state.sm.event_bus,
            store,
            package="provider",
            changes={"from_address": "second@test"},
        )
        await finalize_session(db)
    assert core_mail.current_mail_sender().from_address == "second@test"
    view = next(v for v in collect_module_settings(app) if v.package == "mail")
    assert next(f for f in view.fields if f.name == "backend").choices == [
        "console",
        "http-api",
        "smtp",
    ]


@pytest.mark.parametrize(
    ("raw", "value_type", "expected"),
    [("worker@test", "string", "worker@test"), ("3", "int", "default@example.com")],
)
async def test_worker_registration_and_resolver_use_provider_settings(
    provider, db_session, raw, value_type, expected
):
    MailModule().register_event_handlers(EventBus(), None)
    store = SettingsStore(SettingService(db_session))
    await store.set_override("mail", "backend", "http-api", "string")
    await store.set_override("provider", "from_address", raw, value_type)
    sender = await core_mail.resolve_mail_sender(db_session)
    assert isinstance(sender, ProviderSender)
    assert sender.from_address == expected


async def test_unknown_transport_is_rejected_by_admin(app, db_session):
    with pytest.raises(ValidationError, match="Unknown choice for backend"):
        await apply_changes_and_reload(
            app,
            app.state.sm.event_bus,
            SettingsStore(SettingService(db_session)),
            package="mail",
            changes={"backend": "uninstalled"},
        )


async def test_worker_unknown_transport_does_not_silently_use_console(db_session, monkeypatch):
    await SettingsStore(SettingService(db_session)).set_override(
        "mail", "backend", "uninstalled", "string"
    )
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="Unknown mail transport"):
        await resolve_sender_from_db(db_session)


def test_unknown_transport_refuses_app_startup_outside_development():
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(settings=SimpleNamespace(environment="testing")),
            mail=SimpleNamespace(settings=MailSettings(backend="uninstalled")),
        )
    )
    with pytest.raises(ValueError, match="Unknown mail transport"):
        install_app_sender(app)


async def test_startup_and_provider_reload_build_selected_transport(provider):
    from settings.contracts.events import SettingsReloaded

    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(settings=SimpleNamespace(environment="development")),
            mail=SimpleNamespace(settings=MailSettings(backend="http-api")),
            provider=SimpleNamespace(settings=ProviderSettings(from_address="startup@test")),
        )
    )
    bus = EventBus()
    module = MailModule()
    module.register_event_handlers(bus, app)
    await module.on_startup(app)
    assert core_mail.current_mail_sender().from_address == "startup@test"
    app.state.provider.settings = ProviderSettings(from_address="reload@test")
    await bus.publish(SettingsReloaded(package="provider", changed=("from_address",)))
    assert core_mail.current_mail_sender().from_address == "reload@test"
    await bus.publish(SettingsReloaded(package="mail", changed=("smtp_host",)))
    assert core_mail.current_mail_sender().from_address == "reload@test"
    explicit = CapturedMail()
    core_mail.install_mail_sender(explicit)
    await bus.publish(SettingsReloaded(package="mail", changed=("smtp_host",)))
    assert core_mail.current_mail_sender() is explicit


async def test_outbox_delivers_through_registered_transport(
    provider, db_session, db_state, monkeypatch
):
    from dataclasses import dataclass

    from background_tasks.outbox.claim import OutboxPolicy
    from background_tasks.outbox.dispatch import dispatch
    from background_tasks.outbox.transport import WorkerOutboxTransport
    from mail.contracts import register_mail_transport
    from simple_module_core.eventing.events import Event

    @dataclass
    class SendViaProvider(Event):
        message: core_mail.MailMessage

    delivered = []

    class RecordingProvider(ProviderSender):
        async def send(self, message):
            delivered.append((self.from_address, message))

    register_mail_transport(
        "outbox-http", RecordingProvider, settings_model=ProviderSettings, package="provider"
    )
    bus = EventBus()
    MailModule().register_event_handlers(bus, None)

    async def deliver(event, ctx):
        await (await core_mail.resolve_mail_sender(ctx.db)).send(event.message)

    bus.subscribe_durable(SendViaProvider, deliver, name="registered-transport-test")
    transport = WorkerOutboxTransport()
    monkeypatch.setattr(transport, "schedule", lambda db, ids: None)
    bus.durable_transport = transport
    store = SettingsStore(SettingService(db_session))
    await store.set_override("mail", "backend", "outbox-http", "string")
    await store.set_override("provider", "from_address", "outbox@test", "string")
    await bus.publish_durable(
        SendViaProvider(core_mail.MailMessage("to@test", "Provider", "Body")), db_session
    )
    await db_session.commit()
    result = await dispatch(
        db_state.session_factory, bus, OutboxPolicy(max_attempts=8, lease_seconds=300)
    )
    assert result.delivered == 1
    assert delivered[0][0] == "outbox@test"
    assert delivered[0][1].subject == "Provider"
