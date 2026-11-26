"""Every bundled module's settings field has a translated label.

The settings editor labels a field from ``<package>.settings_form.fields.<name>.label``
and a group heading from ``<package>.settings_form.groups.<slug>``. Without the
key it falls back to a humanised identifier, which reads poorly and is never
translated. This guard keeps a newly added field from shipping that way.
Locale parity across languages is checked by the i18n lint, so English is the
reference here.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings

REPO = Path(__file__).resolve().parents[5]
# Modules whose fields are edited on their own page (``manage_url``); the
# generic editor shows only their title.
OWN_PAGE = {"branding"}


def group_slug(group: str) -> str:
    """Mirror of ``groupSlug`` in ``settings/ui/utils/field-text.ts``."""
    return re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_")


def _bundled_settings() -> list[tuple[str, type[BaseSettings]]]:
    found: list[tuple[str, type[BaseSettings]]] = []
    for path in sorted(REPO.glob("modules/*/*/core/settings.py")):
        package = path.parents[1].name
        module = importlib.import_module(f"{package}.core.settings")
        for cls in vars(module).values():
            if (
                inspect.isclass(cls)
                and issubclass(cls, BaseSettings)
                and cls.__module__ == module.__name__
                and cls.model_fields
            ):
                found.append((package, cls))
    return found


def _en(package: str) -> dict:
    path = REPO / "modules" / package / package / "locales" / "en.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("package", "cls"),
    _bundled_settings(),
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_every_settings_field_has_an_english_label(package: str, cls: type) -> None:
    form = _en(package).get("settings_form", {})
    missing: list[str] = []
    if not form.get("title"):
        missing.append("settings_form.title")
    if package not in OWN_PAGE:
        fields = form.get("fields", {})
        groups = form.get("groups", {})
        for name, info in cls.model_fields.items():
            if not fields.get(name, {}).get("label"):
                missing.append(f"settings_form.fields.{name}.label")
            extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
            group = extra.get("group")
            if isinstance(group, str) and not groups.get(group_slug(group)):
                missing.append(f"settings_form.groups.{group_slug(group)}")
    assert not missing, f"{package}: missing en.json keys: {sorted(set(missing))}"


def test_group_slug_matches_the_client_rule() -> None:
    assert group_slug("Demo account") == "demo_account"
    assert group_slug("S3") == "s3"
    assert group_slug(" Google OAuth ") == "google_oauth"
