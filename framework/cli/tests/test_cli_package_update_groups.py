"""Dependency-array and workspace regressions for #715."""

import pytest
from simple_module_cli.package_update import run_update


@pytest.mark.parametrize("dry_run", [False, True])
def test_group_only_root_and_optional_arrays(tmp_path, fake_pypi, dry_run, capsys):
    path = tmp_path / "pyproject.toml"
    original = """[dependency-groups]
dev = [
  "simple_module_test[extra]==0.1; python_version >= '3.12'", # keep me
  {include-group = "tools"},
]
tools = ["simple_module_cli==0.1"]
[project.optional-dependencies]
extra = ["simple_module_db>=0.1,<3", "other==1"]
"""
    path.write_text(original)
    run_update(
        tmp_path,
        dry_run=dry_run,
        fetcher=fake_pypi(
            {"simple_module_test": "1.0", "simple_module_cli": "1.0", "simple_module_db": "1.0"}
        ),
    )
    expected = original if dry_run else original.replace("==0.1", "==1.0").replace(">=0.1", ">=1.0")
    assert path.read_text() == expected
    assert "3 dependency(ies) across 1 file(s)" in capsys.readouterr().out


def test_workspace_sources_override_and_members_are_deduplicated(tmp_path, fake_pypi, capsys):
    (tmp_path / "pyproject.toml").write_text(
        """[dependency-groups]
dev = ["simple_module_cli==0.1"]
[tool.uv.workspace]
members = ["modules/*", "modules/a"]
[tool.uv.sources]
Simple.Module.Core = {path = "core"}
""".replace("Simple.Module.Core", '"Simple.Module.Core"')
    )
    member = tmp_path / "modules/a/pyproject.toml"
    member.parent.mkdir(parents=True)
    member.write_text("""[dependency-groups]
dev = ["simple_module_core==0.1", "simple_module_test==0.1"]
[tool.uv.sources]
"simple-module-test" = [{path = "test", marker = "sys_platform == 'linux'"}]
""")
    run_update(
        tmp_path,
        fetcher=fake_pypi(
            {"simple_module_core": "2.0", "simple_module_cli": "2.0", "simple_module_test": "2.0"}
        ),
    )
    assert '"simple_module_core==0.1"' in member.read_text()
    assert '"simple_module_test==0.1"' in member.read_text()
    assert capsys.readouterr().out.count("workspace/local source") == 2


def test_member_index_override_of_root_source(tmp_path, fake_pypi):
    (tmp_path / "pyproject.toml").write_text("""[tool.uv.workspace]
members = ["a"]
[tool.uv.sources]
"simple-module-test" = {path = "test"}
""")
    member = tmp_path / "a/pyproject.toml"
    member.parent.mkdir()
    member.write_text("""[dependency-groups]
dev = ["simple_module_test==0.1"]
[tool.uv.sources]
simple_module_test = {index = "pypi"}
""")
    run_update(tmp_path, fetcher=fake_pypi({"simple_module_test": "1.0"}))
    assert '"simple_module_test==1.0"' in member.read_text()
