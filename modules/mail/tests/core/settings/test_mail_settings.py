"""Sender validation and safe hydration of legacy mail settings."""

import pytest
from mail.core.settings import MailSettings
from pydantic import ValidationError
from simple_module_core.settings.settings_hydrate import build_settings

_LONG_ADDRESS = "a" * 64 + "@" + ".".join(["b" * 63, "c" * 63, "d" * 61])


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "not-an-address",
        "sender@",
        '"',
        "sender@[",
        "sender@a.\u200b.de",
        "sender@" + "é" * 64 + ".de",
        "@example.com",
        "sender@example..com",
        "sender@example.com, other@example.com",
        "Senders: sender@example.com;",
        "Sender <sender@example.com",
        "sender@example.com>",
        "sender@example.com garbage",
        "Sender <sender@example.com> garbage",
        "sender@example.com\r\nBcc: other@example.com",
        "\nsender@example.com",
        "sender@example.com\r",
        "\tsender@example.com",
        "sender@example.com\v",
        "\fsender@example.com",
        "Sender\x00 <sender@example.com>",
        "Sender\x7f <sender@example.com>",
        "x" * 1200,
        _LONG_ADDRESS + "d",
        "N" * 300 + " <sender@example.com>",
    ],
)
def test_smtp_from_rejects_invalid_mailboxes(value):
    with pytest.raises(ValidationError) as exc:
        MailSettings(smtp_from=value)
    error = exc.value.errors()[0]
    assert error["loc"] == ("smtp_from",)
    assert "smtp_from" in error["msg"]


@pytest.mark.parametrize(
    "value",
    [
        "sender@example.com",
        "no-reply@localhost",
        "Example Team <sender@example.com>",
        '"Doe, Jane" <sender@example.com>',
        "Jäne <sender@bücher.de>",
        "sender@" + "é" * 57 + ".de",
        "jäne@example.com",
        _LONG_ADDRESS,
        "N" * 299 + " <sender@example.com>",
    ],
)
def test_smtp_from_preserves_valid_mailboxes_and_trims_outer_spaces(value):
    assert MailSettings(smtp_from=f"  {value}  ").smtp_from == value


@pytest.mark.parametrize(
    "value",
    ["   ", "invalid", "x" * 1200, "a@test\nBcc: b@test", '"', "sender@[", "sender@a.\u200b.de"],
)
def test_invalid_stored_sender_falls_back_without_losing_other_settings(value, caplog):
    stored = {"smtp_from": (value, "string"), "smtp_port": ("2525", "int")}
    cfg = build_settings(MailSettings, stored, lenient=True)
    assert cfg.smtp_from == "no-reply@localhost"
    assert cfg.smtp_port == 2525
    assert stored["smtp_from"] == (value, "string")
    assert "Ignoring stored value for MailSettings.smtp_from" in caplog.text
