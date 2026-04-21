"""Tests for the datasets module's feature flags + settings wiring."""

from __future__ import annotations

import json

import httpx
import pytest
from datasets import constants
from simple_module_core.feature_flags import FeatureFlagRegistry

GEOJSON_PAYLOAD = json.dumps({"type": "FeatureCollection", "features": []}).encode()


class TestFeatureFlags:
    """Verify the module registered the flags it advertises and that the
    upload endpoint honours the flag toggles."""

    async def test_flags_registered(self, app):
        registry: FeatureFlagRegistry = app.state.sm.feature_flags
        names = {flag.name for flag in registry.all_flags}
        assert constants.FLAG_AUTO_EXTRACT in names
        assert constants.FLAG_ALLOW_RASTER_UPLOADS in names

    async def test_auto_extract_default_on_enqueues_task(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.post(
            "/api/datasets/",
            data={"name": "Flag On"},
            files={"file": ("a.geojson", GEOJSON_PAYLOAD, "application/geo+json")},
        )
        assert resp.status_code == 201, resp.text
        app.state.background_tasks.celery.send_task.assert_called_once()

    async def test_disabling_auto_extract_skips_task(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        """With the flag off, the upload still succeeds but no Celery task
        is enqueued — rows stay ``pending`` until an admin retriggers
        extraction."""
        registry: FeatureFlagRegistry = app.state.sm.feature_flags
        registry._flags[constants.FLAG_AUTO_EXTRACT] = registry._flags[
            constants.FLAG_AUTO_EXTRACT
        ].__class__(
            name=constants.FLAG_AUTO_EXTRACT,
            description="...",
            default_enabled=False,
        )
        try:
            resp = await authenticated_client.post(
                "/api/datasets/",
                data={"name": "Flag Off"},
                files={"file": ("a.geojson", GEOJSON_PAYLOAD, "application/geo+json")},
            )
            assert resp.status_code == 201
            app.state.background_tasks.celery.send_task.assert_not_called()
            assert resp.json()["extraction_status"] == constants.ExtractionStatus.PENDING
        finally:
            # Restore the default-on definition for other tests.
            from simple_module_core.feature_flags import FeatureFlagDefinition

            registry._flags[constants.FLAG_AUTO_EXTRACT] = FeatureFlagDefinition(
                name=constants.FLAG_AUTO_EXTRACT,
                description="...",
                default_enabled=True,
            )

    async def test_raster_uploads_rejected_when_flag_off(
        self, app, authenticated_client: httpx.AsyncClient
    ):
        from simple_module_core.feature_flags import FeatureFlagDefinition

        registry: FeatureFlagRegistry = app.state.sm.feature_flags
        registry._flags[constants.FLAG_ALLOW_RASTER_UPLOADS] = FeatureFlagDefinition(
            name=constants.FLAG_ALLOW_RASTER_UPLOADS,
            description="...",
            default_enabled=False,
        )
        try:
            resp = await authenticated_client.post(
                "/api/datasets/",
                data={"name": "Big Raster", "kind": constants.DatasetKind.RASTER_GEOTIFF},
                files={"file": ("a.tif", b"\x00" * 128, "image/tiff")},
            )
            assert resp.status_code == 422
            assert "raster" in resp.json()["detail"].lower()
        finally:
            registry._flags[constants.FLAG_ALLOW_RASTER_UPLOADS] = FeatureFlagDefinition(
                name=constants.FLAG_ALLOW_RASTER_UPLOADS,
                description="...",
                default_enabled=True,
            )


class TestSettings:
    """Settings module registers runtime-tunable knobs at ``on_startup``."""

    async def test_max_upload_mb_registered(self, app):
        """The settings module may not be installed in every deployment;
        when it is, the ``datasets.max_upload_mb`` key shows up in the
        registry with the env default as its fallback."""
        settings_state = getattr(app.state, "settings", None)
        if settings_state is None:
            pytest.skip("settings module not installed")
        registry = settings_state.registry
        definition = registry.get(constants.SETTING_MAX_UPLOAD_MB)
        assert definition is not None
        assert definition.default == str(constants.DEFAULT_MAX_UPLOAD_MB)

    async def test_default_kind_registered(self, app):
        settings_state = getattr(app.state, "settings", None)
        if settings_state is None:
            pytest.skip("settings module not installed")
        registry = settings_state.registry
        definition = registry.get(constants.SETTING_DEFAULT_KIND)
        assert definition is not None


class TestPermissionsMapping:
    """``register_permissions`` maps the ``user`` role to view+upload so
    plain users can self-serve without becoming admins."""

    async def test_user_role_includes_view_and_upload(self, app):
        registry = app.state.sm.permissions
        perms = set(registry.role_map.get(constants.ROLE_USER, []))
        assert constants.PERM_DATASETS_VIEW in perms
        assert constants.PERM_DATASETS_UPLOAD in perms
        # Edit / delete stay admin-only.
        assert constants.PERM_DATASETS_EDIT not in perms
        assert constants.PERM_DATASETS_DELETE not in perms
