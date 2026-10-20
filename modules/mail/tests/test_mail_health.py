"""The ``mail.smtp`` check re-reads the installed sender on every run."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mail.runtime import check_smtp
from mail.sender import SmtpMailSender
from simple_module_core import mail as core_mail
from simple_module_core.health import HealthStatus
from simple_module_core.mail import ConsoleMailSender


async def test_console_is_healthy_without_a_connection() -> None:
    core_mail.install_mail_sender(ConsoleMailSender())
    result = await check_smtp()
    assert result.status is HealthStatus.HEALTHY
    assert "needs no connection" in result.detail


async def test_nothing_installed_is_also_healthy() -> None:
    core_mail.install_mail_sender(None)
    assert (await check_smtp()).status is HealthStatus.HEALTHY


@pytest.fixture
def smtp_client(monkeypatch) -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock()
    client.login = AsyncMock()
    client.quit = AsyncMock()
    monkeypatch.setattr("mail.sender.aiosmtplib.SMTP", MagicMock(return_value=client))
    core_mail.install_mail_sender(SmtpMailSender("h", 587, "user", "pw", "f@test", True))
    return client


async def test_smtp_reachable(smtp_client) -> None:
    result = await check_smtp()
    assert result.status is HealthStatus.HEALTHY
    smtp_client.login.assert_awaited_once_with("user", "pw")
    smtp_client.quit.assert_awaited_once()


async def test_smtp_failure_reports_the_reason(smtp_client) -> None:
    smtp_client.login.side_effect = RuntimeError("authentication failed")
    result = await check_smtp()
    assert result.status is HealthStatus.UNHEALTHY
    assert result.detail == "authentication failed"
    smtp_client.quit.assert_awaited_once()


async def test_the_check_is_registered_on_demand_only(app) -> None:
    checks = {c.name: c for c in app.state.sm.health_registry.all_checks}
    assert checks["mail.smtp"].probe is False
    assert checks["mail.smtp"].module == "Mail"
