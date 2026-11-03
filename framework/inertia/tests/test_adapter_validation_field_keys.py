"""Validation locations describe form fields, not nested error details (#776)."""

import pytest
from simple_module_inertia import errors_from_validation


@pytest.mark.parametrize("source", [None, "body", "query", "path", "header", "cookie", "form"])
@pytest.mark.parametrize("path", [("address", "city"), ("tags", 0), ("quantity", "int"), (7,)])
def test_validation_uses_first_field_after_optional_source(source, path):
    loc = path if source is None else (source, *path)
    assert errors_from_validation(
        iter([{"loc": loc, "msg": "first"}, {"loc": loc, "msg": "last"}]), request_source=True
    ) == {str(path[0]): "first"}


@pytest.mark.parametrize("loc", [(), ("body",)])
def test_validation_without_field_uses_general(loc):
    errors = [{"loc": loc, "msg": "invalid"}]
    assert errors_from_validation(errors, request_source=True) == {"general": "invalid"}


def test_validation_without_errors_is_empty():
    assert errors_from_validation([]) == {}


@pytest.mark.parametrize("field", ["path", "query", "body"])
def test_model_field_named_like_a_request_source_keeps_its_key(field):
    """A model_validate error has no source prefix, so ``path`` is the field."""
    loc = (field, "int")
    assert errors_from_validation([{"loc": loc, "msg": "bad"}]) == {field: "bad"}
