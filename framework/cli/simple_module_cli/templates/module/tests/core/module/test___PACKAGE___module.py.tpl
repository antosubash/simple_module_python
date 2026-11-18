"""Tests for the {{MODULE_NAME}} module feature."""

# ruff: noqa: I001

from __future__ import annotations

from simple_module_test import effective_route_paths

from {{PACKAGE_NAME}}.module import {{MODULE_NAME}}Module


class TestMeta:
    def test_meta_name(self):
        assert {{MODULE_NAME}}Module.meta.name == "{{MODULE_NAME}}"

    def test_meta_requires_framework(self):
        assert {{MODULE_NAME}}Module.meta.requires_framework is not None


class TestBoot:
    async def test_app_boots_with_module(self, build_test_app):
        """Module registers cleanly into a minimal FastAPI host."""
        app = build_test_app({{MODULE_NAME}}Module)
        # effective_route_paths reads the OpenAPI schema: FastAPI >= 0.137
        # includes routers lazily, so ``app.routes`` no longer lists them.
        paths = effective_route_paths(app)
        assert any(p.startswith("/api/{{MODULE_SLUG}}") for p in paths)
