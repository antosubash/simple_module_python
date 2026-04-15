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
with the dev-default secret (or whatever ``SM_USERS_VERIFICATION_TOKEN_SECRET``
is set to).  The server verifies tokens with the same secret, so minting
locally is equivalent to what the ConsoleMailer would have logged — without
needing to scrape server stdout.
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
def reset_token_secret() -> str:
    """The same secret the server uses to sign password-reset JWTs."""
    return os.environ.get(
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
        "dev-reset-token-secret-change-me",
    )


@pytest.fixture(scope="session")
def verify_token_secret() -> str:
    """The same secret the server uses to sign verify/invite JWTs."""
    return os.environ.get(
        "SM_USERS_VERIFICATION_TOKEN_SECRET",
        "dev-verify-token-secret-change-me",
    )


# ---------------------------------------------------------------------------
# Token-minting helpers
# ---------------------------------------------------------------------------


def mint_verify_token(user_id: str, email: str, secret: str) -> str:
    """Mint a fastapi-users verification/invite token locally.

    The token shape mirrors what ``UserManager.generate_verification_token``
    produces, so the server's ``/api/users/auth/accept-invite`` endpoint
    accepts it without modification.

    Audience: ``"fastapi-users:verify"`` — same as the invite flow.
    Lifetime: 3600 seconds (sufficient for a test run).
    """
    from fastapi_users.jwt import generate_jwt

    return generate_jwt(
        {"sub": user_id, "email": email, "aud": "fastapi-users:verify"},
        secret,
        3600,
    )
