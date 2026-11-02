"""Hydrated backend construction shared by sync worker APIs and tasks."""

from file_storage import constants
from file_storage.backends import build_backend
from file_storage.contracts.service import StorageBackend
from file_storage.settings import FileStorageSettings


def backend_and_settings() -> tuple[StorageBackend, FileStorageSettings]:
    from background_tasks.worker_settings import settings_for

    settings = settings_for(FileStorageSettings, constants.MODULE_NAME)
    return build_backend(settings), settings
