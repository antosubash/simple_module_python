"""Refuse object access through a provider that does not own the row."""

from file_storage.contracts.service import StorageBackend
from file_storage.models import StoredFile


class BackendUnavailableError(Exception):
    """The file's recorded provider is no longer configured."""


def backend_mismatch(backend: StorageBackend, row: StoredFile) -> bool:
    """True when both identities are known and differ."""
    stored_backend = getattr(row, "backend", None)
    active_backend = getattr(backend, "backend_id", None)
    # Minimal adapters may omit identity; only reject a known provider mismatch.
    return (
        isinstance(stored_backend, str)
        and isinstance(active_backend, str)
        and stored_backend != active_backend
    )


def require_backend(backend: StorageBackend, row: StoredFile) -> None:
    """Check before any IO, presigning, or conditional response."""
    if backend_mismatch(backend, row):
        raise BackendUnavailableError(
            "This file is stored on a backend that is no longer configured."
        )
