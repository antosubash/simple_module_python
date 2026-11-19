"""Transport-independent settings business failures."""


class SettingsError(Exception):
    """Base for errors raised by settings services."""


class InternalKeyError(SettingsError):
    """Internal metadata cannot be edited through configuration interfaces."""

    def __init__(self) -> None:
        super().__init__("Internal metadata cannot be edited as a setting")
