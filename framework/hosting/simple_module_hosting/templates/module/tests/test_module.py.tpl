"""Smoke tests for the {{MODULE_NAME}} module.

The ``build_test_app`` and ``fake_event_bus`` fixtures come from the
``simple-module-testing`` pytest plugin (registered via entry_points when
that package is installed). No conftest.py is required.
"""

from __future__ import annotations

from {{PACKAGE_NAME}}.module import {{MODULE_NAME}}Module


class TestMeta:
    def test_meta_name(self):
        assert {{MODULE_NAME}}Module.meta.name == "{{MODULE_NAME}}"

    def test_meta_requires_framework(self):
        assert {{MODULE_NAME}}Module.meta.requires_framework is not None


class TestRoutes:
    async def test_app_boots_with_module(self, build_test_app):
        """Module registers cleanly into a minimal FastAPI host."""
        app = build_test_app({{MODULE_NAME}}Module)
        paths = {getattr(r, "path", None) for r in app.routes}
        # The placeholder GET / endpoint lives under the route_prefix.
        assert any(p and p.startswith("/api/{{MODULE_SLUG}}") for p in paths)
