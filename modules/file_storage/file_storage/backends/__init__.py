"""Storage backend registry — extension point for storage providers.

Built-in providers (filesystem, S3) self-register on import. Third-party
packages add new providers via :func:`register_backend`::

    from file_storage.backends import register_backend
    from file_storage.contracts.service import StorageBackend

    @register_backend("azure_blob")
    def _build(settings) -> StorageBackend:
        return AzureBlobBackend(...)

The factory receives the parsed :class:`FileStorageSettings` so providers
can read their own ``SM_FILE_STORAGE_*`` keys (or extend the settings
class with extra fields). :func:`build_backend` resolves the active
factory by ``settings.backend`` and raises :class:`ConfigurationError`
on an unknown id, listing all currently registered providers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from file_storage.contracts.service import ConfigurationError

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend
    from file_storage.settings import FileStorageSettings

BackendFactory = Callable[["FileStorageSettings"], "StorageBackend"]

_REGISTRY: dict[str, BackendFactory] = {}


def register_backend(backend_id: str) -> Callable[[BackendFactory], BackendFactory]:
    """Decorator that registers a factory under ``backend_id``."""

    def decorator(factory: BackendFactory) -> BackendFactory:
        _REGISTRY[backend_id] = factory
        return factory

    return decorator


def unregister_backend(backend_id: str) -> None:
    """Remove a registered backend. Primarily for tests."""
    _REGISTRY.pop(backend_id, None)


def registered_backends() -> list[str]:
    """Return all currently registered backend ids, sorted."""
    return sorted(_REGISTRY)


def build_backend(settings: FileStorageSettings) -> StorageBackend:
    """Construct the backend selected by ``settings.backend``."""
    factory = _REGISTRY.get(settings.backend)
    if factory is None:
        raise ConfigurationError(
            f"Unknown storage backend {settings.backend!r}. Registered: {registered_backends()}."
        )
    return factory(settings)


# Trigger self-registration of built-in providers. Order is irrelevant; both
# add themselves to the same module-global registry.
from file_storage.backends import filesystem as _filesystem  # noqa: E402,F401
from file_storage.backends import s3 as _s3  # noqa: E402,F401

__all__ = [
    "BackendFactory",
    "build_backend",
    "register_backend",
    "registered_backends",
    "unregister_backend",
]
