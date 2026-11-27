"""Upload routes can depend on the public contract in any import order."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "first_import",
    ["file_storage.contracts", "file_storage.files.service", "file_storage.web.deps"],
)
def test_upload_helpers_are_public_without_import_cycles(first_import):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import {first_import}
import file_storage.contracts as contracts
from file_storage.contracts import FileStorageService, get_file_storage_service
from file_storage.files.service import FileStorageService as InternalService
from file_storage.web.deps import get_file_storage_service as internal_dependency

assert FileStorageService is InternalService
assert get_file_storage_service is internal_dependency
assert {{"FileStorageService", "get_file_storage_service"}} <= set(contracts.__all__)
""",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
