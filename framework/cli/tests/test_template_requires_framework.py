"""The module scaffold's ``requires_framework`` range must admit the current API version."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.specifiers import SpecifierSet
from simple_module_core.versioning import FRAMEWORK_API_VERSION

import simple_module_cli

TEMPLATE = (
    Path(simple_module_cli.__file__).parent
    / "templates"
    / "module"
    / "__PACKAGE__"
    / "module.py.tpl"
)


def test_template_requires_framework_contains_api_version() -> None:
    match = re.search(r'requires_framework="([^"]+)"', TEMPLATE.read_text(encoding="utf-8"))
    assert match, "module.py.tpl no longer declares requires_framework"
    assert FRAMEWORK_API_VERSION in SpecifierSet(match.group(1))
