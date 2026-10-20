"""``get_file_storage_service`` refuses to run before the backend is built."""

import pytest
from file_storage.deps import get_file_storage_service
from file_storage.services import FileStorageServices


async def test_service_dep_requires_backend():
    services = FileStorageServices(settings=None)
    with pytest.raises(RuntimeError, match="not initialised"):
        await get_file_storage_service(db=None, services=services)
