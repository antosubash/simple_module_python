"""Consumers can enforce module layout without copying the framework's test."""

import pytest


def test_public_layout_helper_allows_duplicate_test_basenames(tmp_path):
    from simple_module_test import assert_module_layout

    package = tmp_path / "orders"
    (package / "core").mkdir(parents=True)
    for area in ("core", "web"):
        tests = tmp_path / "tests" / area / "crud"
        tests.mkdir(parents=True)
        (tests / "test_crud.py").touch()
    (package / "fulfillment").mkdir()
    (package / "fulfillment" / "service.py").touch()
    assert_module_layout(tmp_path, "orders", domain_areas={"fulfillment"})


@pytest.mark.parametrize(
    "bad_path", ["orders/service.py", "tests/test_orders.py", "tests/__init__.py"]
)
def test_public_layout_helper_rejects_layout_drift(tmp_path, bad_path):
    from simple_module_test import assert_module_layout

    (tmp_path / "orders").mkdir()
    target = tmp_path / bad_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    with pytest.raises(AssertionError):
        assert_module_layout(tmp_path, "orders")
