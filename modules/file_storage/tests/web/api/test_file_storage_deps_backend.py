"""``get_file_storage_service`` refuses to run before the backend is built."""

import pytest
from file_storage.core.services import FileStorageServices
from file_storage.web.deps import get_file_storage_service


async def test_service_dep_requires_backend():
    services = FileStorageServices(settings=None)
    with pytest.raises(RuntimeError, match="not initialised"):
        await get_file_storage_service(db=None, services=services)
