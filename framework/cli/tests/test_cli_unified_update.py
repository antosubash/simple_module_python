"""Source-aware updates finish installation, without contacting registries (#984)."""

import json
import tomllib

import pytest
import typer
from simple_module_cli import update_cmd
from simple_module_cli.cli import app
from typer.testing import CliRunner


@pytest.mark.parametrize("workspace", [False, True])
def test_update_bumps_pypi_and_git_then_syncs(tmp_path, fake_pypi, workspace):
    root = tmp_path / "pyproject.toml"
    host = tmp_path / "host" if workspace else tmp_path
    host.mkdir(exist_ok=True)
    if workspace:
        root.write_text('[tool.uv.workspace]\nmembers = ["host"]\n')
    project = host / "pyproject.toml"
    project.write_text(
        '[project]\nname = "app"\nversion = "0"\n'
        'dependencies = ["simple_module_core==0.0.46", "simple_module_blog>=0.1,<1"]\n'
        "[tool.uv.sources]\n"
        'simple_module_blog = {git = "https://example.com/blog", tag = "v0.1.0"}\n'
    )
    client = host / "client_app"
    client.mkdir()
    npm = tmp_path if workspace else client
    (npm / "package.json").write_text(json.dumps({"dependencies": {"react": "^19"}}))
    calls = []

    def execute(cmd, cwd):
        calls.append((cmd, cwd))
        return 0

    update_cmd.run_update(
        project,
        fetcher=fake_pypi({"simple_module_core": "0.0.47"}),
        git_runner=lambda *a, **k: "sha\trefs/tags/v0.2.0\n",
        exec_runner=execute,
    )
    data = tomllib.loads(project.read_text())
    assert data["project"]["dependencies"] == [
        "simple_module_core==0.0.47",
        "simple_module_blog>=0.2.0,<1",
    ]
    assert data["tool"]["uv"]["sources"]["simple_module_blog"]["tag"] == "v0.2.0"
    assert calls == [
        (["uv", "sync", "--all-packages"] if workspace else ["uv", "sync"], tmp_path),
        (["npm", "install"], npm),
        (["uv", "run", "smpy", "gen"], tmp_path),
    ]


@pytest.mark.parametrize("fail_at", [0, 1, 2])
def test_update_stops_at_failed_install_step(tmp_path, fake_pypi, fail_at, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0"\ndependencies = ["simple_module_core==0.0.46"]\n'
    )
    (tmp_path / "client_app").mkdir()
    (tmp_path / "client_app/package.json").write_text("{}")
    calls = []

    def execute(cmd, cwd):
        calls.append(cmd)
        return 1 if len(calls) == fail_at + 1 else 0

    with pytest.raises(typer.Exit):
        update_cmd.run_update(
            tmp_path, fetcher=fake_pypi({"simple_module_core": "0.0.47"}), exec_runner=execute
        )
    assert len(calls) == fail_at + 1
    assert "failed" in capsys.readouterr().err


def test_alias_warns_and_forwards_options(tmp_path, fake_pypi, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0"\ndependencies = ["simple_module_core==0.0.46"]\n'
    )
    monkeypatch.setattr(
        "simple_module_cli.package_update.default_fetcher",
        fake_pypi({"simple_module_core": "0.0.47"}),
    )
    before = (tmp_path / "pyproject.toml").read_bytes()
    with pytest.warns(DeprecationWarning, match="0.0.50"):
        result = CliRunner().invoke(
            app, ["package-update", "--path", str(tmp_path), "--dry-run", "--loosen"]
        )
    assert result.exit_code == 0, result.output
    assert "simple_module_core>=0.0.47" in result.output
    assert (tmp_path / "pyproject.toml").read_bytes() == before


@pytest.mark.parametrize("only", [None, "simple-module-blog"])
def test_workspace_inherited_git_core_keeps_npm_in_lockstep(tmp_path, only):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["host"]\n[tool.uv.sources]\n'
        'simple-module-core = {git = "https://example.com/fw", tag = "v0.0.46"}\n'
        'simple-module-blog = {git = "https://example.com/fw", tag = "v0.0.46"}\n'
    )
    host = tmp_path / "host"
    host.mkdir()
    (host / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0"\n'
        'dependencies = ["simple_module_core==0.0.46", "simple_module_blog>=0.0.46,<1"]\n'
    )
    (host / "client_app").mkdir()
    manifest = tmp_path / "package.json"
    manifest.write_text('{"dependencies":{"@simple-module-py/ui":"^0.0.46"}}')
    urls = []

    def fetch(url):
        urls.append(url)
        assert "registry.npmjs.org" in url
        return {"versions": {"0.0.47": {}}}

    update_cmd.run_update(
        host,
        only=only,
        fetcher=fetch,
        git_runner=lambda *a, **k: "sha\trefs/tags/v0.0.47\n",
        exec_runner=lambda *a: 0,
    )
    assert "simple_module_core==0.0.47" in (host / "pyproject.toml").read_text()
    assert json.loads(manifest.read_text())["dependencies"]["@simple-module-py/ui"] == "^0.0.47"
    assert len(urls) == 1


def test_named_update_does_not_touch_other_pypi_pins(tmp_path, fake_pypi):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0"\n'
        'dependencies = ["simple_module_core==0.0.46", "simple_module_db==0.0.46"]\n'
    )
    calls = []
    update_cmd.run_update(
        tmp_path,
        only="simple-module-db",
        fetcher=fake_pypi({"simple_module_db": "0.0.47"}),
        exec_runner=lambda cmd, cwd: calls.append(cmd) or 0,
    )
    assert tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]["dependencies"] == [
        "simple_module_core==0.0.46",
        "simple_module_db==0.0.47",
    ]
    assert calls == [["uv", "sync"]]


def test_git_update_does_not_downgrade_a_newer_tag(tmp_path):
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\nname="app"\nversion="0"\ndependencies=["simple_module_blog"]\n'
        "[tool.uv.sources]\n"
        'simple_module_blog={git="https://example.com/blog",tag="v0.3.0"}\n'
    )
    before = project.read_bytes()
    update_cmd.run_update(
        tmp_path,
        fetcher=lambda url: {},
        git_runner=lambda *a, **k: "sha\trefs/tags/v0.2.0\n",
        exec_runner=lambda *a: 0,
    )
    assert project.read_bytes() == before


def test_nonworkspace_npm_manifests_are_both_installed(tmp_path, fake_pypi):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="app"\nversion="0"\n')
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "client_app").mkdir()
    (tmp_path / "client_app/package.json").write_text("{}")
    calls = []
    update_cmd.run_update(
        tmp_path,
        fetcher=fake_pypi({}),
        exec_runner=lambda cmd, cwd: calls.append((cmd, cwd)) or 0,
    )
    assert calls == [
        (["uv", "sync"], tmp_path),
        (["npm", "install"], tmp_path),
        (["npm", "install"], tmp_path / "client_app"),
        (["uv", "run", "smpy", "gen"], tmp_path),
    ]


def test_npm_workspace_install_covers_its_members_once(tmp_path, fake_pypi):
    (tmp_path / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers=["host"]\n')
    (tmp_path / "package.json").write_text('{"workspaces":["host/client_app"]}')
    host = tmp_path / "host"
    host.mkdir()
    (host / "pyproject.toml").write_text('[project]\nname="host"\nversion="0"\n')
    (host / "package.json").write_text("{}")
    (host / "client_app").mkdir()
    (host / "client_app/package.json").write_text("{}")
    calls = []
    update_cmd.run_update(
        tmp_path,
        fetcher=fake_pypi({}),
        exec_runner=lambda cmd, cwd: calls.append((cmd, cwd)) or 0,
    )
    assert calls == [
        (["uv", "sync", "--all-packages"], tmp_path),
        (["npm", "install"], tmp_path),
        (["npm", "install"], host),
        (["uv", "run", "smpy", "gen"], tmp_path),
    ]


def test_missing_project_in_workspace_does_not_update_the_workspace(tmp_path, fake_pypi):
    project = tmp_path / "pyproject.toml"
    project.write_text('[tool.uv.workspace]\nmembers=["modules/*"]\n')
    module = tmp_path / "modules/empty"
    module.mkdir(parents=True)
    calls = []
    with pytest.raises(typer.Exit):
        update_cmd.run_update(
            module,
            fetcher=fake_pypi({}),
            exec_runner=lambda cmd, cwd: calls.append(cmd) or 0,
        )
    assert calls == []
