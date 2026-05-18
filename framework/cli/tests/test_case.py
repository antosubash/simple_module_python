"""Direct unit tests for the identifier case helpers.

Every scaffolder pipes a user-supplied module name through these — a typo
that emits ``u_r_l_path`` from ``URLPath`` would propagate into the PyPI
slug *and* the display name. Existing tests touch ``to_pascal_case`` only
indirectly via ``test_helpers.py``; we pin the snake/kebab forms too,
including the acronym edge cases the docstring promises.
"""

from __future__ import annotations

import pytest
from simple_module_cli.case import to_kebab_case, to_pascal_case, to_snake_case


class TestToSnakeCase:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("MyFeature", "my_feature"),
            ("my-feature", "my_feature"),
            ("my_feature", "my_feature"),
            ("My Feature", "my_feature"),
            ("MY_FEATURE", "my_feature"),
            ("URLPath", "url_path"),
            ("APIClient", "api_client"),
            ("HTTPServer2", "http_server2"),
            ("simple", "simple"),
            ("simple-thing-name", "simple_thing_name"),
            ("Already_Snake_Mixed", "already_snake_mixed"),
            ("trailing-", "trailing_"),
        ],
    )
    def test_canonicalises(self, raw, expected):
        assert to_snake_case(raw) == expected


class TestToKebabCase:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("MyFeature", "my-feature"),
            ("my_feature", "my-feature"),
            ("URLPath", "url-path"),
        ],
    )
    def test_canonicalises(self, raw, expected):
        assert to_kebab_case(raw) == expected


class TestToPascalCase:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("my-feature", "MyFeature"),
            ("my_feature", "MyFeature"),
            ("MyFeature", "MyFeature"),
            ("URLPath", "UrlPath"),  # consequence of the snake-cased pipeline
            ("__name__", "Name"),  # empty parts dropped
        ],
    )
    def test_canonicalises(self, raw, expected):
        assert to_pascal_case(raw) == expected
