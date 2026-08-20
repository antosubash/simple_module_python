"""Tests for git-side resolution: ref classification, shallow clone, repo scan."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.git_source import (
    RefInfo,
    classify_ref,
    list_remote_refs,
    scan_modules,
    shallow_clone,
)


def _uri(repo: Path) -> str:
    return repo.as_uri()


class TestRefs:
    def test_list_remote_refs(self, make_git_module_repo) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)], tags=["v0.1.0"])
        tags, branches = list_remote_refs(_uri(repo))
        assert "v0.1.0" in tags
        assert "main" in branches

    def test_classify_tag_branch_rev_default(self, make_git_module_repo) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)], tags=["v0.1.0"])
        url = _uri(repo)
        assert classify_ref(url, None) == RefInfo("default", None)
        assert classify_ref(url, "v0.1.0") == RefInfo("tag", "v0.1.0")
        assert classify_ref(url, "main") == RefInfo("branch", "main")
        assert classify_ref(url, "0123abc") == RefInfo("rev", "0123abc")


class TestCloneAndScan:
    def test_clone_default_and_scan_single(self, make_git_module_repo, tmp_path) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, True)])
        dest = tmp_path / "clone1"
        shallow_clone(_uri(repo), RefInfo("default", None), dest)
        found = scan_modules(dest)
        assert len(found) == 1
        mod = found[0]
        assert mod.dist_name == "simple_module_blog"
        assert mod.version == "0.2.0"
        assert mod.subdirectory is None
        assert mod.ships_models is True
        assert mod.framework_range == ">=0.1,<1.0"

    def test_clone_at_tag(self, make_git_module_repo, tmp_path) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)], tags=["v0.1.0"])
        dest = tmp_path / "clone2"
        shallow_clone(_uri(repo), RefInfo("tag", "v0.1.0"), dest)
        assert (dest / "pyproject.toml").is_file()

    def test_scan_multi_module_repo(self, make_git_module_repo, tmp_path) -> None:
        repo = make_git_module_repo(
            [
                ("simple_module_blog", "0.1.0", "modules/blog", False),
                ("simple_module_comments", "0.1.0", "modules/comments", True),
            ],
            extra_pyproject_dirs=["tools/scripts"],
        )
        dest = tmp_path / "clone3"
        shallow_clone(_uri(repo), RefInfo("default", None), dest)
        found = scan_modules(dest)
        names = {m.dist_name: m for m in found}
        assert set(names) == {"simple_module_blog", "simple_module_comments"}
        assert names["simple_module_blog"].subdirectory == "modules/blog"
        assert names["simple_module_comments"].ships_models is True
