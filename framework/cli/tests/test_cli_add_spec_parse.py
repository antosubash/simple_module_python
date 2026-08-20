"""Tests for `smpy add` spec parsing and version helpers."""

from __future__ import annotations

import pytest
from simple_module_cli.git_source import (
    SpecError,
    derive_range,
    parse_add_spec,
    pick_latest_tag,
    satisfies,
    version_tuple,
)


def test_pypi_spec_passthrough() -> None:
    p = parse_add_spec("simple_module_blog>=1.2,<2.0")
    assert p.kind == "pypi"
    assert p.raw == "simple_module_blog>=1.2,<2.0"


def test_git_spec_plain() -> None:
    p = parse_add_spec("git+https://github.com/x/repo")
    assert p.kind == "git"
    assert p.git is not None
    assert p.git.url == "https://github.com/x/repo"
    assert p.git.ref is None
    assert p.git.subdirectory is None


def test_git_spec_with_ref_and_subdirectory() -> None:
    p = parse_add_spec("git+https://github.com/x/repo@v1.2.0#subdirectory=modules/blog")
    assert p.git is not None
    assert p.git.url == "https://github.com/x/repo"
    assert p.git.ref == "v1.2.0"
    assert p.git.subdirectory == "modules/blog"


def test_git_ssh_userinfo_at_is_not_a_ref() -> None:
    p = parse_add_spec("git+ssh://git@github.com/x/repo")
    assert p.git is not None
    assert p.git.url == "ssh://git@github.com/x/repo"
    assert p.git.ref is None


def test_git_ssh_userinfo_with_ref() -> None:
    p = parse_add_spec("git+ssh://git@github.com/x/repo@main")
    assert p.git is not None
    assert p.git.url == "ssh://git@github.com/x/repo"
    assert p.git.ref == "main"


def test_path_spec() -> None:
    p = parse_add_spec("../mod")
    assert p.kind == "path"


def test_bare_https_url_rejected_with_hint() -> None:
    with pytest.raises(SpecError, match="git\\+"):
        parse_add_spec("https://github.com/x/repo")


def test_unknown_fragment_rejected() -> None:
    with pytest.raises(SpecError, match="subdirectory"):
        parse_add_spec("git+https://github.com/x/repo#egg=foo")


def test_empty_spec_rejected() -> None:
    with pytest.raises(SpecError):
        parse_add_spec("   ")


def test_version_tuple_and_satisfies() -> None:
    assert version_tuple("1.2.3") == (1, 2, 3)
    assert satisfies("1.2.3", ">=1.2,<2.0")
    assert not satisfies("2.0.0", ">=1.2,<2.0")
    assert satisfies("1.2", ">=1.2.0")  # padded comparison
    assert not satisfies("1.2.3", "!=1.2.3")
    assert satisfies("0.5.0", "<1.0")


def test_derive_range() -> None:
    assert derive_range("0.3.2") == ">=0.3.2,<1.0"
    assert derive_range("1.4.0") == ">=1.4.0,<2.0"


def test_pick_latest_tag() -> None:
    tags = ["v0.1.0", "v1.2.0", "v1.10.0", "v2.0.0", "not-a-version", "release-3"]
    assert pick_latest_tag(tags, ">=1.0,<2.0") == "v1.10.0"
    assert pick_latest_tag(tags, None) == "v2.0.0"
    assert pick_latest_tag(["nope"], None) is None
