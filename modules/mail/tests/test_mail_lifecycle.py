"""Startup installs the sender, a reload reinstalls it, the resolver reads the DB."""

from __future__ import annotations

from mail.sender import SmtpMailSender
from settings.contracts.events import SettingsReloaded
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.store import SettingsStore
from simple_module_core import mail as core_mail
from simple_module_core.mail import ConsoleMailSender, resolve_mail_sender
from simple_module_db.transaction import finalize_session


async def test_startup_installs_the_configured_sender(app) -> None:
    sender = core_mail.current_mail_sender()
    assert isinstance(sender, ConsoleMailSender)
    assert sender.include_body is True  # the explicit backend, not the fallback


async def test_a_settings_reload_reinstalls_the_sender(app) -> None:
    # Use the app's own session: the reload re-reads the committed DB state.
    async with app.state.sm.db.session_factory() as db:
        store = SettingsStore(SettingService(db))
        await apply_changes_and_reload(
            app,
            app.state.sm.event_bus,
            store,
            package="mail",
            changes={"backend": "smtp", "smtp_host": "smtp.test"},
        )
        await finalize_session(db)  # the reload runs after commit
    assert isinstance(core_mail.current_mail_sender(), SmtpMailSender)


async def test_another_packages_reload_is_ignored(app) -> None:
    before = core_mail.current_mail_sender()
    await app.state.sm.event_bus.publish(SettingsReloaded(package="users", changed=("x",)))
    assert core_mail.current_mail_sender() is before


async def test_the_resolver_is_installed_and_shutdown_clears_both(app) -> None:
    assert core_mail._resolver is not None
    module = next(m for m in app.state.sm.modules if m.meta.name == "Mail")
    await module.on_shutdown(app)
    assert core_mail._sender is None and core_mail._resolver is None


async def test_the_resolver_hydrates_stored_settings(app, db_session) -> None:
    core_mail.install_mail_sender(None)
    store = SettingsStore(SettingService(db_session))
    await store.set_override("mail", "backend", "smtp", "string")
    await store.set_override("mail", "smtp_host", "db.test", "string")
    await store.set_override("mail", "smtp_port", "2525", "int")

    sender = await resolve_mail_sender(db_session)

    assert isinstance(sender, SmtpMailSender)
    assert (sender._host, sender._port) == ("db.test", 2525)


async def test_the_resolver_falls_back_to_console_without_rows(app, db_session) -> None:
    core_mail.install_mail_sender(None)
    sender = await resolve_mail_sender(db_session)
    assert isinstance(sender, ConsoleMailSender)
