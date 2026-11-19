"""Users signing keys come from one root, with a dated legacy-env escape hatch."""

import pytest
from fastapi_users.jwt import decode_jwt, generate_jwt
from users.core.token_secrets import resolve_token_secrets

RESET_ENV = "SM_USERS_RESET_PASSWORD_TOKEN_SECRET"
VERIFY_ENV = "SM_USERS_VERIFICATION_TOKEN_SECRET"


@pytest.fixture(autouse=True)
def clear_legacy_env(monkeypatch):
    monkeypatch.delenv(RESET_ENV, raising=False)
    monkeypatch.delenv(VERIFY_ENV, raising=False)


def test_default_keys_are_derived_and_separated():
    secrets = resolve_token_secrets("root-key")
    assert secrets.reset_password_token_secret == "B-157_tKXq37K_3qKmFVBePx4PkHqa45I2q8BtNKu1I="
    assert secrets.verification_token_secret == "Woju4GtBslB0jXk9qvgpqf-YnQ4MYxDcec1RYM1pZXY="
    assert secrets.verification_token_secret != secrets.reset_password_token_secret
    assert secrets == resolve_token_secrets("root-key")


@pytest.mark.parametrize("padding", ["", " \t"])
@pytest.mark.parametrize(
    ("env", "field", "audience"),
    [
        (RESET_ENV, "reset_password_token_secret", "fastapi-users:reset"),
        (VERIFY_ENV, "verification_token_secret", "fastapi-users:verify"),
    ],
)
def test_explicit_legacy_key_still_verifies_existing_tokens(
    monkeypatch, caplog, env, field, audience, padding
):
    key = "explicit-old-key-at-least-32-bytes-long"
    token = generate_jwt({"sub": "existing-user", "aud": audience}, key, 3600)
    monkeypatch.setenv(env, padding + key + padding)
    secrets = resolve_token_secrets("a-different-root-key")
    assert decode_jwt(token, getattr(secrets, field), [audience])["sub"] == "existing-user"
    assert env in caplog.text and "0.0.50" in caplog.text
    assert key not in caplog.text


@pytest.mark.parametrize("padding", ["", " \t\n"])
def test_placeholders_and_empty_env_values_use_derived_keys(monkeypatch, padding):
    expected = resolve_token_secrets("root-key")
    monkeypatch.setenv(RESET_ENV, padding + "dev-reset-token-secret-change-me" + padding)
    monkeypatch.setenv(VERIFY_ENV, padding + "dev-verify-token-secret-change-me" + padding)
    assert resolve_token_secrets("root-key") == expected
    monkeypatch.setenv(RESET_ENV, padding)
    monkeypatch.setenv(VERIFY_ENV, padding)
    assert resolve_token_secrets("root-key") == expected


def test_module_registration_uses_resolved_root_before_services_exist():
    from auth.module import AuthModule
    from simple_module_hosting._app_boot import build_fastapi_app
    from simple_module_hosting.settings import Settings
    from users.module import UsersModule

    settings = Settings(_env_file=None, environment="testing", secret_key="resolved-root")
    app = build_fastapi_app(settings, lifespan=None)
    AuthModule().register_settings(app)
    UsersModule().register_settings(app)
    assert app.state.users.token_secrets.reset_password_token_secret == (
        resolve_token_secrets("resolved-root").reset_password_token_secret
    )
    # Settings hydration replaces this object at startup and on reloads.
    from users.core.settings import UsersSettings

    app.state.users.settings = UsersSettings()
    assert app.state.users.token_secrets.verification_token_secret == (
        resolve_token_secrets("resolved-root").verification_token_secret
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_existing_manager_uses_current_services_root(monkeypatch, legacy):
    from types import SimpleNamespace

    from auth.module import AuthModule
    from simple_module_hosting._app_boot import build_fastapi_app
    from simple_module_hosting.settings import Settings
    from users.accounts.manager import UserManager
    from users.core.settings import UsersSettings
    from users.module import UsersModule

    if legacy:
        monkeypatch.setenv(RESET_ENV, "explicit-reset-key-at-least-32-bytes")
        monkeypatch.setenv(VERIFY_ENV, "explicit-verify-key-at-least-32-bytes")
    settings = Settings(_env_file=None, environment="testing", secret_key="ephemeral-root")
    app = build_fastapi_app(settings, lifespan=None)
    AuthModule().register_settings(app)
    UsersModule().register_settings(app)
    manager = UserManager(None, None, UsersSettings(), app.state.users.token_secrets)
    app.state.sm = SimpleNamespace(
        settings=settings.model_copy(update={"secret_key": "stored-root"})
    )
    for field, audience in [
        ("reset_password_token_secret", "fastapi-users:reset"),
        ("verification_token_secret", "fastapi-users:verify"),
    ]:
        token = generate_jwt({"sub": "user", "aud": audience}, getattr(manager, field), 3600)
        assert decode_jwt(token, getattr(resolve_token_secrets("stored-root"), field), [audience])
