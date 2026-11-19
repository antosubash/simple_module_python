"""Fixtures for end-to-end browser tests.

These tests drive a real Chromium browser against a running stack
(`make docker-up` + `make dev`). They are gated by the ``e2e`` pytest marker
(declared in ``pyproject.toml``) and excluded from the default suite.

Env vars:
    E2E_BASE_URL  — where the FastAPI host is listening (default: http://localhost:8000)
    E2E_USERNAME  — admin email address (default: admin@example.com)
    E2E_PASSWORD  — admin password (default: admin)
    E2E_USER_ID   — UUID of the E2E admin user (optional; enables password-reset test)

Token-minting helpers
---------------------
:func:`mint_verify_token` builds a fastapi-users verify/invite token signed
with the key derived from the same explicit ``SM_SECRET_KEY`` as the server.
Minting locally is equivalent to what the ConsoleMailer would have logged,
without needing to scrape server stdout.
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Base fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def e2e_username() -> str:
    return os.environ.get("E2E_USERNAME", "admin@example.com")


@pytest.fixture(scope="session")
def e2e_password() -> str:
    return os.environ.get("E2E_PASSWORD", "admin")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, base_url):
    """Override pytest-playwright's context args to set base_url.

    With this in place, ``page.goto("/")`` resolves relative to E2E_BASE_URL.
    """
    return {**browser_context_args, "base_url": base_url}


# ---------------------------------------------------------------------------
# Token-secret fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def token_secrets():
    """Local token minting needs the same explicit root as the running server."""
    from users.core.token_secrets import resolve_token_secrets

    root = os.environ.get("SM_SECRET_KEY")
    if not root:
        pytest.skip("Local token minting requires the server's SM_SECRET_KEY")
    return resolve_token_secrets(root)


@pytest.fixture(scope="session")
def reset_token_secret(token_secrets) -> str:
    return token_secrets.reset_password_token_secret


@pytest.fixture(scope="session")
def verify_token_secret(token_secrets) -> str:
    return token_secrets.verification_token_secret


# ---------------------------------------------------------------------------
# Token-minting helpers
# ---------------------------------------------------------------------------


def mint_verify_token(user_id: str, email: str, secret: str) -> str:
    """Mint a fastapi-users verification/invite token locally.

    The token shape mirrors what ``UserManager.mint_invite_token`` produces, so
    the server's ``/api/users/auth/accept-invite`` endpoint accepts it without
    modification.

    Audience: ``"fastapi-users:verify"`` — same as the invite flow.
    Lifetime: 3600 seconds (sufficient for a test run).
    """
    from fastapi_users.jwt import generate_jwt

    return generate_jwt(
        {"sub": user_id, "email": email, "aud": "fastapi-users:verify"},
        secret,
        3600,
    )
