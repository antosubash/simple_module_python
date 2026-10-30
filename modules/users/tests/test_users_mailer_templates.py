"""Host template precedence, optional HTML, and startup configuration (#712)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from jinja2 import TemplateNotFound, TemplateSyntaxError
from jinja2.exceptions import SecurityError
from simple_module_core.settings_hydrate import build_settings
from users.mailer import build_mailer
from users.mailer.templated import TemplatedMailer
from users.settings import UsersSettings
from users.startup import _build_mailer


@pytest.mark.parametrize(
    ("stem", "method", "args", "route"),
    [
        ("verify_email", "send_verification", (), "verify"),
        ("reset_password", "send_password_reset", (), "reset-password"),
        ("invite", "send_invite", ("<Alice>", " <note> "), "invite/accept"),
    ],
)
async def test_html_only_override_keeps_bundled_text(
    tmp_path, captured_mail, stem, method, args, route
):
    (tmp_path / f"{stem}.html").write_text(
        "<p>{{ app_name }}|{{ link }}|{{ invited_by_name }}|{{ message }}</p>"
    )
    mailer = TemplatedMailer("https://example.com/", lambda: "<Acme>", template_dirs=[tmp_path])
    await getattr(mailer, method)("a@example.com", "tok&x", *args)

    (msg,) = captured_mail.messages
    assert f"https://example.com/users/{route}?token=tok&x" in msg.text
    assert "<Acme>" in msg.text
    assert f"https://example.com/users/{route}?token=tok&amp;x" in msg.html
    assert "&lt;Acme&gt;" in msg.html
    if stem == "invite":
        assert "&lt;Alice&gt;|&lt;note&gt;" in msg.html
        assert "<Alice>" in msg.text and "<note>" in msg.text


async def test_directory_order_and_independent_file_fallback(tmp_path, captured_mail):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "verify_email.txt").write_text("first {{ app_name }}")
    (second / "verify_email.txt").write_text("second")
    (second / "verify_email.html").write_text("<b>second {{ app_name }}</b>")
    mailer = build_mailer(UsersSettings(), lambda: "<Acme>", template_dirs=[str(first), second])
    await mailer.send_verification("a@example.com", "tok")
    await mailer.send_password_reset("a@example.com", "reset")
    verify, reset = captured_mail.messages
    assert verify.text == "first <Acme>"
    assert verify.html == "<b>second &lt;Acme&gt;</b>"
    assert "/users/reset-password?token=reset" in reset.text
    assert reset.html is None


async def test_mailer_environments_are_isolated(tmp_path, captured_mail):
    (tmp_path / "verify_email.txt").write_text("custom")
    custom = TemplatedMailer("https://example.com", template_dirs=[tmp_path])
    default = TemplatedMailer("https://example.com")
    await custom.send_verification("a@example.com", "tok")
    await default.send_verification("a@example.com", "tok")
    await custom.send_verification("a@example.com", "tok")
    assert [m.text for m in captured_mail.messages][::2] == ["custom", "custom"]
    assert "Welcome to SimpleModule!" in captured_mail.messages[1].text
    assert all(m.html is None for m in captured_mail.messages)


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("{% if %}", TemplateSyntaxError),
        ('{% include "missing.html" %}', TemplateNotFound),
        ('{% extends "missing.html" %}', TemplateNotFound),
        ("{{ 1 / 0 }}", ZeroDivisionError),
    ],
)
async def test_broken_html_prevents_delivery(tmp_path, captured_mail, source, error):
    (tmp_path / "verify_email.html").write_text(source)
    mailer = TemplatedMailer("https://example.com", template_dirs=[tmp_path])
    with pytest.raises(error):
        await mailer.send_verification("a@example.com", "tok")
    assert not captured_mail.messages


async def test_broken_text_is_not_hidden_by_bundled_fallback(tmp_path, captured_mail):
    (tmp_path / "verify_email.txt").write_text("{% if %}")
    mailer = TemplatedMailer("https://example.com", template_dirs=[tmp_path])
    with pytest.raises(TemplateSyntaxError):
        await mailer.send_verification("a@example.com", "tok")
    assert not captured_mail.messages


@pytest.mark.parametrize("kind", ["relative", "missing", "file"])
def test_invalid_template_directory_is_skipped_with_warning(tmp_path, kind, caplog):
    path = tmp_path / kind
    if kind == "file":
        path.write_text("not a directory")
    if kind == "relative":
        path = Path("relative")
    settings = UsersSettings(mail_template_dirs=[str(path)])
    state = SimpleNamespace()
    _build_mailer(FastAPI(), state, settings)
    assert state.mailer is not None
    assert "Ignoring mail template path" in caplog.text


async def test_startup_forwards_db_setting_and_keeps_branding_live(tmp_path, captured_mail):
    (tmp_path / "verify_email.html").write_text("<p>{{ app_name }}</p>")
    settings = build_settings(
        UsersSettings, {"mail_template_dirs": (json.dumps([str(tmp_path)]), "json")}
    )
    app = FastAPI()
    app.state.branding = SimpleNamespace(settings=SimpleNamespace(app_name="First"))
    state = SimpleNamespace()
    _build_mailer(app, state, settings)
    app.state.branding.settings.app_name = "<Second>"
    await state.mailer.send_verification("a@example.com", "tok")
    (msg,) = captured_mail.messages
    assert msg.html == "<p>&lt;Second&gt;</p>"
    assert msg.subject == "Verify your email for <Second>"
    assert "<Second>" in msg.text


def test_template_setting_is_restart_required_and_defaults_are_independent(monkeypatch):
    monkeypatch.setenv("SM_USERS_MAIL_TEMPLATE_DIRS", '["/ignored"]')
    first, second = UsersSettings(), UsersSettings()
    assert first.mail_template_dirs == []
    first.mail_template_dirs.append("/trusted/templates")
    assert second.mail_template_dirs == []
    assert UsersSettings.model_fields["mail_template_dirs"].json_schema_extra == {
        "requires_restart": True
    }


async def test_host_templates_render_sandboxed(tmp_path, captured_mail):
    # The directory list is admin-editable, so a template must not reach Python
    # internals (the classic ``__class__.__mro__`` escape).
    (tmp_path / "verify_email.txt").write_text("{{ ''.__class__.__mro__[1].__subclasses__() }}")
    mailer = TemplatedMailer("https://example.com", template_dirs=[tmp_path])
    with pytest.raises(SecurityError):
        await mailer.send_verification("a@example.com", "tok")
    assert captured_mail.messages == []
