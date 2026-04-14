"""Tests for pure helper functions in the new_module scaffolding script."""

from __future__ import annotations

from pathlib import Path

import pytest
from new_module import (
    _insert_after_last_match,
    create_file,
    to_class_name,
    to_singular,
    validate_name,
)


class TestValidateName:
    def test_valid_simple_name(self):
        assert validate_name("orders") == "orders"

    def test_valid_name_with_underscore(self):
        assert validate_name("blog_posts") == "blog_posts"

    def test_valid_name_with_digits(self):
        assert validate_name("v2_items") == "v2_items"

    def test_rejects_uppercase(self):
        with pytest.raises(SystemExit):
            validate_name("Orders")

    def test_rejects_hyphens(self):
        with pytest.raises(SystemExit):
            validate_name("blog-posts")

    def test_rejects_starting_with_digit(self):
        with pytest.raises(SystemExit):
            validate_name("2fast")

    def test_rejects_empty(self):
        with pytest.raises(SystemExit):
            validate_name("")


class TestToClassName:
    def test_single_word(self):
        assert to_class_name("orders") == "Orders"

    def test_two_words(self):
        assert to_class_name("blog_posts") == "BlogPosts"

    def test_three_words(self):
        assert to_class_name("user_role_assignments") == "UserRoleAssignments"


class TestToSingular:
    def test_plural(self):
        assert to_singular("orders") == "order"

    def test_already_singular(self):
        assert to_singular("inventory") == "inventory"

    def test_double_s(self):
        assert to_singular("access") == "access"

    def test_plural_compound(self):
        assert to_singular("blog_posts") == "blog_post"


class TestInsertAfterLastMatch:
    def test_inserts_after_last_matching_line(self):
        content = 'dependencies = [\n    "foo",\n    "bar",\n    "baz",\n]\n'
        result = _insert_after_last_match(content, r'^    "[\w]+",\s*$', '    "qux",\n')
        assert result is not None
        assert '"baz",\n    "qux",\n]' in result

    def test_returns_none_when_no_match(self):
        result = _insert_after_last_match("no matches\n", r"^XYZ$", "inserted\n")
        assert result is None

    def test_respects_last_of_many(self):
        # `other = x` between matches must not divert insertion to before it
        content = "sm-a = 1\nsm-b = 2\nother = x\nsm-c = 3\n"
        result = _insert_after_last_match(content, r"^sm-\w+ = \d+$", "sm-d = 4\n")
        assert result is not None
        assert result.endswith("sm-c = 3\nsm-d = 4\n")

    def test_inserts_before_trailing_content(self):
        content = "a = 1\nb = 2\n# trailer\n"
        result = _insert_after_last_match(content, r"^b = 2$", "c = 3\n")
        assert result == "a = 1\nb = 2\nc = 3\n# trailer\n"


class TestCreateFile:
    def test_creates_file_with_content(self, module_root: Path):
        target = module_root / "foo" / "bar.txt"
        create_file(target, "hello world\n")

        assert target.read_text() == "hello world\n"

    def test_creates_parent_directories(self, module_root: Path):
        target = module_root / "a" / "b" / "c" / "file.txt"
        create_file(target, "")

        assert target.exists()
        assert target.parent.is_dir()

    def test_dedents_content(self, module_root: Path):
        target = module_root / "indented.txt"
        create_file(target, "        line one\n        line two\n")

        assert target.read_text() == "line one\nline two\n"
