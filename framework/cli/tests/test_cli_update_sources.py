"""Tests for `smpy update` — git-tag group updates over [tool.uv.sources]."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.update_cmd import run_sources_update


def _host(tmp_path: Path, url: str) -> Path:
    p = tmp_path / "host" / "pyproject.toml"
    p.parent.mkdir()
    p.write_text(
        '[project]\nname = "myhost"\nversion = "0.1.0"\n'
        "dependencies = [\n"
        '    "simple_module_blog>=0.1.0,<1.0",\n'
        '    "simple_module_comments>=0.1.0,<1.0",\n'
        '    "simple_module_dashboard>=0.1",\n'
        "]\n\n"
        "[tool.uv.sources]\n"
        f'simple_module_blog = {{ git = "{url}", tag = "v0.1.0", subdirectory = "modules/blog" }}\n'
        f'simple_module_comments = {{ git = "{url}", tag = "v0.1.0", subdirectory = "modules/comments" }}\n',
        encoding="utf-8",
    )
    return p


def _recorder():
    calls: list[list[str]] = []

    def runner(cmd: list[str], cwd: Path) -> int:
        calls.append(cmd)
        return 0

    return calls, runner


def _git_stub(tags: list[str]):
    def run(args, cwd=None):
        assert args[0] == "ls-remote"
        return "".join(f"sha\trefs/tags/{t}\n" for t in tags) + "sha\trefs/heads/main\n"

    return run


def test_group_update_moves_all_siblings(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    calls, runner = _recorder()
    run_sources_update(
        p,
        only=None,
        dry_run=False,
        git_runner=_git_stub(["v0.1.0", "v0.3.0", "v2.0.0"]),  # v2 excluded by <1.0
        exec_runner=runner,
    )
    text = p.read_text(encoding="utf-8")
    assert text.count('tag = "v0.3.0"') == 2
    assert 'tag = "v0.1.0"' not in text
    # dep floors bumped to the new version
    assert "simple_module_blog>=0.3.0,<1.0" in text
    assert ["uv", "sync"] in calls


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    before = p.read_text(encoding="utf-8")
    calls, runner = _recorder()
    run_sources_update(
        p, only=None, dry_run=True, git_runner=_git_stub(["v0.3.0"]), exec_runner=runner
    )
    assert p.read_text(encoding="utf-8") == before
    assert calls == []


def test_only_limits_to_that_group(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    calls, runner = _recorder()
    run_sources_update(
        p,
        only="simple_module_blog",
        dry_run=False,
        git_runner=_git_stub(["v0.3.0"]),
        exec_runner=runner,
    )
    # group update still moves the sibling — same repo, one ref (spec §3/§4)
    assert p.read_text(encoding="utf-8").count('tag = "v0.3.0"') == 2


def test_pypi_name_delegates_to_uv_lock(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    calls, runner = _recorder()
    run_sources_update(
        p,
        only="simple_module_dashboard",
        dry_run=False,
        git_runner=_git_stub([]),
        exec_runner=runner,
    )
    assert ["uv", "lock", "--upgrade-package", "simple_module_dashboard"] in calls


def test_branch_pin_relocks_and_labels_dev_mode(tmp_path: Path, capsys) -> None:
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project]\nname = "h"\nversion = "0"\n'
        'dependencies = ["simple_module_blog>=0.1,<1.0"]\n\n'
        "[tool.uv.sources]\n"
        'simple_module_blog = { git = "https://github.com/x/b", branch = "main" }\n',
        encoding="utf-8",
    )
    calls, runner = _recorder()
    run_sources_update(p, only=None, dry_run=False, git_runner=_git_stub([]), exec_runner=runner)
    assert ["uv", "lock", "--upgrade-package", "simple_module_blog"] in calls
    assert "dev-mode" in capsys.readouterr().out


def test_no_newer_tag_is_a_quiet_noop(tmp_path: Path, capsys) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    before = p.read_text(encoding="utf-8")
    calls, runner = _recorder()
    run_sources_update(
        p, only=None, dry_run=False, git_runner=_git_stub(["v0.1.0"]), exec_runner=runner
    )
    assert p.read_text(encoding="utf-8") == before
    assert "up to date" in capsys.readouterr().out
