"""Shared validation for automatically assigned signup roles."""

from users.core.constants import ADMIN_ROLE_NAME


def _validate_signup_role(value: str, error_message: str) -> str:
    value = value.strip()
    if value.lower() == ADMIN_ROLE_NAME:
        raise ValueError(error_message)
    return value
