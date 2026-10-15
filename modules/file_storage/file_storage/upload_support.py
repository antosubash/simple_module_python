"""Errors and part arithmetic for resumable uploads (#454)."""

from __future__ import annotations

import math
import uuid
from typing import TYPE_CHECKING

from file_storage import constants

if TYPE_CHECKING:
    from file_storage.models import UploadSession


class UploadNotFoundError(Exception):
    """No such session for this user in this tenant (also: someone else's)."""


class UploadClosedError(Exception):
    """The session is completed, aborted or past its deadline."""


class DirectUploadUnsupportedError(Exception):
    """The active backend cannot do multipart uploads."""


class QuotaExceededError(Exception):
    """The file would not fit in the configured storage quota."""


class InvalidPartError(Exception):
    """A part number outside the file, or a part of the wrong size."""


class PartsMismatchError(Exception):
    """The backend does not hold the parts the client claims to have sent."""

    def __init__(self, missing: list[int], mismatched: list[int]) -> None:
        super().__init__(f"missing={missing} mismatched={mismatched}")
        self.missing = missing
        self.mismatched = mismatched


class SizeMismatchError(Exception):
    """The assembled object is not the size the session promised."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected {expected} bytes, assembled {actual}")
        self.expected = expected
        self.actual = actual


def choose_part_size(total_size: int, preferred: int) -> int:
    """``preferred``, grown (in whole MiB) until the file needs <= 10,000 parts."""
    needed = math.ceil(total_size / constants.MAX_UPLOAD_PARTS)
    size = max(preferred, needed)
    return math.ceil(size / constants.MIB) * constants.MIB


def total_parts(session: UploadSession) -> int:
    return math.ceil(session.total_size / session.part_size)


def expected_part_size(session: UploadSession, part_no: int) -> int:
    if part_no < total_parts(session):
        return session.part_size
    return session.total_size - (total_parts(session) - 1) * session.part_size


def part_path(upload_id: uuid.UUID, part_no: int) -> str:
    """The app route that relays a part, for backends that cannot presign."""
    return constants.ROUTE_PREFIX_API + constants.PATH_UPLOAD_PART.format(
        upload_id=upload_id, part_no=part_no
    )
