"""Tests for the backend registry — the extension point for new providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from file_storage import constants
from file_storage.backends import (
    build_backend,
    register_backend,
    registered_backends,
    unregister_backend,
)
from file_storage.contracts.service import ConfigurationError, StorageBackend
from file_storage.settings import FileStorageSettings


class _DummyBackend:
    """Bare-minimum StorageBackend for registry tests."""

    backend_id = "dummy"
    supports_presigned_url = False

    async def put(self, key: str, stream: AsyncIterator[bytes], **kwargs: Any) -> None:
        async for _ in stream:
            pass

    async def get(self, key: str) -> AsyncIterator[bytes]:  # pragma: no cover - unused
        async def empty() -> AsyncIterator[bytes]:
            if False:
                yield b""

        return empty()

    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool:
        return False

    async def presigned_get_url(self, key: str, ttl_seconds: int) -> str:  # pragma: no cover
        raise NotImplementedError


def test_builtin_backends_are_registered():
    ids = registered_backends()
    assert constants.BackendId.FILESYSTEM in ids
    assert constants.BackendId.S3 in ids


def test_dummy_backend_can_register_and_resolve(tmp_path):
    @register_backend("dummy")
    def _factory(settings: FileStorageSettings) -> StorageBackend:
        return _DummyBackend()

    try:
        settings = FileStorageSettings(backend="dummy", fs_root_path=str(tmp_path))
        backend = build_backend(settings)
        assert backend.backend_id == "dummy"
        assert "dummy" in registered_backends()
    finally:
        unregister_backend("dummy")


def test_unknown_backend_raises_configuration_error(tmp_path):
    settings = FileStorageSettings(backend="bogus", fs_root_path=str(tmp_path))
    with pytest.raises(ConfigurationError) as exc_info:
        build_backend(settings)
    # Error must list the available backends so misconfigured prods can self-diagnose.
    msg = str(exc_info.value)
    assert constants.BackendId.FILESYSTEM in msg
    assert constants.BackendId.S3 in msg


def test_inertia_page_literal_matches_constant():
    """SM003/SM004 require a string literal in inertia.render(); guard the duplication."""
    from file_storage.endpoints import views

    text = Path(views.__file__).read_text()
    assert f'"{constants.PAGE_BROWSE}"' in text, (
        f"views.py must contain the literal {constants.PAGE_BROWSE!r} to satisfy SM003."
    )


def test_filesystem_factory_resolves_root(tmp_path):
    settings = FileStorageSettings(
        backend=constants.BackendId.FILESYSTEM,
        fs_root_path=str(tmp_path),
    )
    backend = build_backend(settings)
    assert backend.backend_id == constants.BackendId.FILESYSTEM
    assert backend.supports_presigned_url is False
