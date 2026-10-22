"""Refuse object access through a provider that does not own the row."""

from file_storage.contracts.service import StorageBackend
from file_storage.models import StoredFile


class BackendUnavailableError(Exception):
    """The file's recorded provider is no longer configured."""


def require_backend(backend: StorageBackend, row: StoredFile) -> None:
    """Check before any IO, presigning, or conditional response."""
    stored_backend = getattr(row, "backend", None)
    active_backend = getattr(backend, "backend_id", None)
    # Minimal adapters may omit identity; only reject a known provider mismatch.
    if (
        isinstance(stored_backend, str)
        and isinstance(active_backend, str)
        and stored_backend != active_backend
    ):
        raise BackendUnavailableError(
            "This file is stored on a backend that is no longer configured."
        )
