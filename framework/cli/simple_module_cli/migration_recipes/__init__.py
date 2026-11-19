"""Frozen source for the two data upgrades bundled with ``smpy``."""

from importlib.resources import files


def mail_settings() -> tuple[str, str]:
    return "mail", files(__package__).joinpath("mail_settings.py").read_text(encoding="utf-8")


def users_tokens() -> tuple[str, str]:
    return "users", files(__package__).joinpath("users_tokens.py").read_text(encoding="utf-8")
