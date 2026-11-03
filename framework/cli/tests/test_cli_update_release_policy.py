"""Updates keep release exclusions and compatibility policy across runs."""

import tomllib
from pathlib import Path

import pytest
from simple_module_cli.package_update import run_update
from simple_module_cli.update_cmd import run_sources_update


@pytest.mark.parametrize(("version", "yanked"), [("0.0.43rc1", False), ("0.0.43", True)])
def test_package_update_without_eligible_releases_keeps_manifest(
    tmp_path: Path, capsys, version: str, yanked: bool
) -> None:
    path = tmp_path / "pyproject.toml"
    original = '[project]\nname="host"\nversion="0"\ndependencies=["simple_module_core==0.0.42"]\n'
    path.write_text(original)

    def fetcher(url: str) -> dict:
        return {
            "info": {"version": version},
            "releases": {version: [{"yanked": yanked}]},
        }

    run_update(path, include_pre=False, fetcher=fetcher)

    assert path.read_text() == original
    assert "No updates applied." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("policy", "tags", "selected", "expected"),
    [
        (
            ">=0.1,<0.4,!=0.3.1",
            ["v0.3.0", "v0.3.1", "v0.8.0"],
            "v0.3.0",
            ">=0.3.0,<0.4,!=0.3.1",
        ),
        (
            ">=0.1,<=0.3.0,!=0.2.0",
            ["v0.2.0", "v0.3.0", "v0.8.0"],
            "v0.3.0",
            ">=0.3.0,<=0.3.0,!=0.2.0",
        ),
        ("~=0.1", ["v0.3.0", "v1.0.0"], "v0.3.0", "~=0.3"),
        ("~=0.1.0", ["v0.1.9", "v0.2.0"], "v0.1.9", "~=0.1.9"),
        ("<0.4,!=0.3.1", ["v0.3.0", "v0.3.1", "v0.8.0"], "v0.3.0", "<0.4,!=0.3.1"),
    ],
)
def test_git_update_preserves_policy_on_repeated_runs(
    tmp_path: Path, capsys, policy: str, tags: list[str], selected: str, expected: str
) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nname="host"\nversion="0"\n'
        f'dependencies=["simple_module_blog{policy}"]\n'
        '[tool.uv.sources]\nsimple_module_blog={git="https://example.invalid/blog",'
        'tag="v0.1.0"}\n'
    )

    def git_runner(args, cwd=None):
        assert args == ["ls-remote", "--tags", "--heads", "https://example.invalid/blog"]
        return "".join(f"sha\trefs/tags/{tag}\n" for tag in tags)

    for attempt in range(2):
        before = path.read_bytes()
        run_sources_update(
            path, only=None, dry_run=False, git_runner=git_runner, exec_runner=lambda *a: 0
        )
        data = tomllib.loads(path.read_text())
        assert data["project"]["dependencies"] == [f"simple_module_blog{expected}"]
        assert data["tool"]["uv"]["sources"]["simple_module_blog"]["tag"] == selected
        output = capsys.readouterr().out
        if attempt:
            assert path.read_bytes() == before
            assert "up to date" in output
