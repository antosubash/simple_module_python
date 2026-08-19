"""Tests for `smpy add` — end-to-end against local git fixture repos."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from simple_module_cli.add_cmd import run_add

HOST = '[project]\nname = "myhost"\nversion = "0.1.0"\ndependencies = ["simple_module_core>=0.1,<1.0"]\n'


@pytest.fixture
def host_pyproject(tmp_path: Path) -> Path:
    p = tmp_path / "host" / "pyproject.toml"
    p.parent.mkdir()
    p.write_text(HOST, encoding="utf-8")
    return p


def _recorder():
    calls: list[list[str]] = []

    def runner(cmd: list[str], cwd: Path) -> int:
        calls.append(cmd)
        return 0

    return calls, runner


def test_add_single_module_from_git(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, True)], tags=["v0.2.0"])
    calls, runner = _recorder()
    added = run_add(
        f"git+{repo.as_uri()}@v0.2.0",
        pyproject=host_pyproject,
        exec_runner=runner,
    )
    assert added == ["simple_module_blog"]
    text = host_pyproject.read_text(encoding="utf-8")
    assert "simple_module_blog>=0.2.0,<1.0" in text
    assert 'tag = "v0.2.0"' in text
    assert ["uv", "sync"] in calls  # post-install pipeline ran


def test_add_multi_module_select(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo(
        [
            ("simple_module_blog", "0.1.0", "modules/blog", False),
            ("simple_module_comments", "0.1.0", "modules/comments", False),
        ]
    )
    _, runner = _recorder()
    added = run_add(
        f"git+{repo.as_uri()}",
        pyproject=host_pyproject,
        select=["simple_module_comments"],
        exec_runner=runner,
    )
    assert added == ["simple_module_comments"]
    text = host_pyproject.read_text(encoding="utf-8")
    assert 'subdirectory = "modules/comments"' in text
    assert "simple_module_blog" not in text


def test_add_multi_module_all(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo(
        [
            ("simple_module_blog", "0.1.0", "modules/blog", False),
            ("simple_module_comments", "0.1.0", "modules/comments", False),
        ]
    )
    _, runner = _recorder()
    added = run_add(
        f"git+{repo.as_uri()}",
        pyproject=host_pyproject,
        all_modules=True,
        exec_runner=runner,
    )
    assert sorted(added) == ["simple_module_blog", "simple_module_comments"]


def test_add_multi_module_without_selection_fails_listing_options(
    make_git_module_repo, host_pyproject, capsys
) -> None:
    repo = make_git_module_repo(
        [
            ("simple_module_blog", "0.1.0", "modules/blog", False),
            ("simple_module_comments", "0.1.0", "modules/comments", False),
        ]
    )
    _, runner = _recorder()
    with pytest.raises(typer.Exit):
        run_add(
            f"git+{repo.as_uri()}",
            pyproject=host_pyproject,
            assume_yes=True,  # non-interactive, no --module/--all
            exec_runner=runner,
        )
    err = capsys.readouterr().err
    assert "simple_module_blog" in err and "simple_module_comments" in err
    # nothing written on failure
    assert "tool.uv.sources" not in host_pyproject.read_text(encoding="utf-8")


def test_add_repo_without_entry_point_fails_with_hint(
    tmp_path, make_git_module_repo, host_pyproject, capsys
) -> None:
    repo = make_git_module_repo([], extra_pyproject_dirs=["lib"])
    _, runner = _recorder()
    with pytest.raises(typer.Exit):
        run_add(f"git+{repo.as_uri()}", pyproject=host_pyproject, exec_runner=runner)
    assert "entry-points.simple_module" in capsys.readouterr().err
    assert host_pyproject.read_text(encoding="utf-8") == HOST


def test_first_git_add_prints_security_notice(make_git_module_repo, host_pyproject, capsys) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)])
    _, runner = _recorder()
    run_add(f"git+{repo.as_uri()}", pyproject=host_pyproject, exec_runner=runner)
    out = capsys.readouterr().out
    assert "URL you chose" in out


def test_models_module_prints_migration_reminder(
    make_git_module_repo, host_pyproject, capsys
) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, True)])
    _, runner = _recorder()
    run_add(f"git+{repo.as_uri()}", pyproject=host_pyproject, exec_runner=runner)
    assert "migration" in capsys.readouterr().out.lower()


def test_no_sync_writes_but_skips_pipeline(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)])
    calls, runner = _recorder()
    run_add(
        f"git+{repo.as_uri()}",
        pyproject=host_pyproject,
        no_sync=True,
        exec_runner=runner,
    )
    assert calls == []
    assert "simple_module_blog" in host_pyproject.read_text(encoding="utf-8")


def test_pypi_spec_adds_plain_dependency(host_pyproject) -> None:
    _, runner = _recorder()
    added = run_add(
        "simple_module_dashboard>=0.1,<1.0",
        pyproject=host_pyproject,
        exec_runner=runner,
    )
    assert added == ["simple_module_dashboard"]
    assert "simple_module_dashboard>=0.1,<1.0" in host_pyproject.read_text(encoding="utf-8")


def test_path_spec_adds_editable_source(tmp_path, make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo([("simple_module_local", "0.1.0", None, False)])
    _, runner = _recorder()
    added = run_add(str(repo), pyproject=host_pyproject, exec_runner=runner)
    assert added == ["simple_module_local"]
    text = host_pyproject.read_text(encoding="utf-8")
    assert "editable = true" in text
