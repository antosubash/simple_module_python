"""App-owned identity defaults survive settings hydration (#1225)."""

from html import escape
from types import SimpleNamespace

import pytest
from simple_module_core.settings.module_settings import module_settings_registry
from simple_module_core.settings.settings_hydrate import build_settings
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.frontend._inertia_shared import merge_shared_prop_providers
from simple_module_inertia import Head
from starlette.requests import Request


@pytest.mark.parametrize(
    "name,stored,expected",
    [
        (None, None, "SimpleModule"),
        ("Acme & Co", None, "Acme & Co"),
        ("Acme", "Database Brand", "Database Brand"),
        ("Acme", "SimpleModule", "SimpleModule"),
    ],
)
@pytest.mark.parametrize("branding", [False, True])
async def test_name_reaches_api_branding_mail_and_document(
    settings, isolated_host_root, captured_mail, name, stored, expected, branding
):
    from branding.module import BrandingModule
    from users.core.startup import _build_mailer

    updates = {"modules_enabled": [], "multi_tenant": False}
    if stored is not None:
        updates["api_title"] = stored
    settings = settings.model_copy(update=updates)
    app = create_app(settings, app_name=name)
    try:
        assert app.openapi()["info"]["title"] == expected
        assert settings.api_title == (stored or "SimpleModule"), "caller settings are unchanged"
        if branding:
            from settings.module import SettingsModule

            SettingsModule().register_settings(app)
            module = BrandingModule()
            module.register_settings(app)
            await module.on_startup(app)

        # Use the registered classes, exactly as boot and hot reload do.
        registry = module_settings_registry(app)
        for package in ("host", "branding") if branding else ("host",):
            cls = registry.get(package)
            field = "api_title" if package == "host" else "app_name"
            overrides = {field: (stored, "string")} if stored is not None else {}
            getattr(app.state, package).settings = build_settings(cls, overrides)
        assert app.state.host.settings.api_title == expected
        if branding:
            assert app.state.branding.settings.app_name == expected
            assert app.state.settings.registry.get("branding.app_name").default == (
                name or "SimpleModule"
            )

        from users.core.settings import UsersSettings

        users = SimpleNamespace(settings=UsersSettings(base_url="https://example.org"))
        app.state.users = users
        _build_mailer(app, users, users.settings)
        await users.mailer.send_password_reset("person@example.org", "token")
        assert captured_mail.messages[-1].subject == f"Reset your {expected} password"
        assert expected in captured_mail.messages[-1].text

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})
        shared = {}
        await merge_shared_prop_providers(app, request, shared)
        assert shared["branding"]["appName"] == expected
        inertia = app.state.inertia_dependency(request)
        bare = await inertia.render("Probe")
        assert f">{escape(expected)}</title>" in bare.body.decode()
        titled = await inertia.render("Probe", head=Head(title="Welcome"))
        assert f">Welcome — {escape(expected)}</title>" in titled.body.decode()
    finally:
        await app.state.sm.db.engine.dispose()


@pytest.mark.parametrize("source", ["explicit", "environment"])
async def test_create_app_preserves_api_title(settings, isolated_host_root, monkeypatch, source):
    from simple_module_hosting.config.settings import Settings

    values = settings.model_dump(exclude={"api_title"})
    values["modules_enabled"] = []
    if source == "environment":
        monkeypatch.setenv("SM_API_TITLE", "Operator API")
    else:
        values["api_title"] = "Operator API"
    app = create_app(Settings(**values), app_name="Acme")
    try:
        assert app.title == "Operator API"
    finally:
        await app.state.sm.db.engine.dispose()


async def test_names_are_app_local(settings, isolated_host_root):
    from branding.module import BrandingModule
    from settings.module import SettingsModule

    apps = []
    try:
        for name in ("First", "Second", None):
            app = create_app(settings.model_copy(update={"modules_enabled": []}), app_name=name)
            apps.append(app)
            SettingsModule().register_settings(app)
            BrandingModule().register_settings(app)
        assert [app.state.branding.settings.app_name for app in apps] == [
            "First",
            "Second",
            "SimpleModule",
        ]
        assert [app.state.host.settings.api_title for app in apps] == [
            "First",
            "Second",
            "SimpleModule",
        ]
    finally:
        for app in apps:
            await app.state.sm.db.engine.dispose()


async def test_branding_override_and_reset_preserve_code_default(settings, isolated_host_root):
    from branding.module import BrandingModule
    from settings.module import SettingsModule

    app = create_app(settings.model_copy(update={"modules_enabled": []}), app_name="Acme")
    try:
        SettingsModule().register_settings(app)
        BrandingModule().register_settings(app)
        cls = module_settings_registry(app).get("branding")
        assert build_settings(cls, {"app_name": ("Database Brand", "string")}).app_name == (
            "Database Brand"
        )
        assert build_settings(cls, {}).app_name == "Acme"
        assert build_settings(cls, {"app_name": ("SimpleModule", "string")}).app_name == (
            "SimpleModule"
        )
    finally:
        await app.state.sm.db.engine.dispose()
