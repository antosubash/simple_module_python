"""Tests for the {{MODULE_NAME}} contracts feature."""

# ruff: noqa: I001

from __future__ import annotations

import pytest
from pydantic import ValidationError

from {{PACKAGE_NAME}}.contracts.schemas import {{SINGULAR_CLASS}}Create, {{SINGULAR_CLASS}}Update


class TestSchemas:
    def test_create_valid(self):
        data = {{SINGULAR_CLASS}}Create(name="Test")
        assert data.name == "Test"
        assert data.description is None

    def test_create_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            {{SINGULAR_CLASS}}Create(name="")

    def test_update_all_optional(self):
        data = {{SINGULAR_CLASS}}Update()
        assert data.name is None
        assert data.is_active is None
