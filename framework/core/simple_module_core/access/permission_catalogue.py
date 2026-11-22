"""String permissions declared once, with their role-editor labels."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar


class PermissionCatalogue(StrEnum):
    """Subclass with ``group=`` and optional ``label_key=`` for registration.

    Members are strings, usable anywhere a permission key is expected. A
    ``(key, label)`` tuple adds an optional human label to the role editor.
    """

    _group_label: ClassVar[str]
    _group_label_key: ClassVar[str]
    label: str

    def __init_subclass__(cls, *, group: str = "", label_key: str = "", **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls._group_label = group or cls.__name__
        cls._group_label_key = label_key

    def __new__(cls, key: str, label: str = ""):
        member = str.__new__(cls, key)
        member._value_ = key
        member.label = label
        return member
