"""Serialized module settings must be props, not live Python objects.

Settings → Modules reflects every installed module's pydantic settings, so the
value types are whatever those modules declared — pydantic has already turned
``media_root: Path`` into a ``PosixPath`` before this screen sees it. Passing
one on untouched puts a value in the Inertia payload that only the HTML render
path can encode, so the page renders on a reload and 500s when an admin clicks
"Settings" in the sidebar.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from settings._module_settings import (
    ModuleSettingField,
    ModuleSettingsView,
)
from settings._module_settings_props import serialize


def _view_with(value: Any, default: Any = "") -> ModuleSettingsView:
    return ModuleSettingsView(
        module_name="Demo",
        package="demo",
        env_prefix="SM_DEMO_",
        class_name="DemoCfg",
        fields=[
            ModuleSettingField(
                name="media_root",
                env_var="SM_DEMO_MEDIA_ROOT",
                value=value,
                default=default,
                description="",
                is_secret=False,
                type="Path",
                requires_restart=False,
                group=None,
            )
        ],
    )


def _only_field(views: list[dict]) -> dict:
    return views[0]["fields"][0]


class TestSerializeProducesJsonSafeProps:
    def test_a_path_value_becomes_a_string(self) -> None:
        result = serialize([_view_with(Path("var/pagebuilder/media"))])

        assert _only_field(result)["value"] == "var/pagebuilder/media"

    def test_a_path_default_becomes_a_string(self) -> None:
        """Defaults reach the payload too — the screen shows both."""
        result = serialize([_view_with("", default=Path("var/media"))])

        assert _only_field(result)["default"] == "var/media"

    @pytest.mark.parametrize(
        "value",
        [Path("var/media"), Decimal("1.5"), date(2026, 8, 21)],
        ids=["path", "decimal", "date"],
    )
    def test_the_payload_survives_a_plain_json_dump(self, value: Any) -> None:
        """The check that matters: Starlette's JSONResponse has no encoder.

        Asserting on ``json.dumps`` rather than on each converted type keeps
        this honest for value types no one has thought of yet.
        """
        result = serialize([_view_with(value)])

        assert json.dumps(result)

    def test_ordinary_values_are_unchanged(self) -> None:
        result = serialize([_view_with(8000, default=25)])
        field = _only_field(result)

        assert field["value"] == 8000
        assert field["default"] == 25

    def test_the_rest_of_the_view_is_intact(self) -> None:
        result = serialize([_view_with(Path("x"))])

        assert result[0]["package"] == "demo"
        assert _only_field(result)["env_var"] == "SM_DEMO_MEDIA_ROOT"
        assert _only_field(result)["source"] == "default"
