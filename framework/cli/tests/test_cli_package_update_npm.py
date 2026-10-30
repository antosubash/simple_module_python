"""Offline npm manifest regressions for #715."""

import json
from urllib.error import HTTPError
from urllib.parse import unquote

import pytest
from simple_module_cli.package_update import run_update


@pytest.fixture
def registry():
    def make(target="1.2.3", missing=()):
        def fetch(url):
            if url.startswith("https://pypi.org/"):
                return {"releases": {target: [{"yanked": False}]}}
            assert url.startswith("https://registry.npmjs.org/")
            name = unquote(url.split("registry.npmjs.org/", 1)[1])
            if name in missing:
                raise HTTPError(url, 404, "missing", {}, None)
            return {"versions": {target: {}}}

        return fetch

    return make


def setup_project(root):
    path = root / "pyproject.toml"
    path.write_text('[project]\ndependencies = ["simple_module_core==0.1.0"]\n')
    return path


@pytest.mark.parametrize("dry_run", [False, True])
def test_npm_all_sections_and_locations(tmp_path, registry, dry_run, capsys):
    (tmp_path / "pyproject.toml").write_text("""[tool.uv.workspace]
members = ["host", "host"]
""")
    host = tmp_path / "host"
    host.mkdir()
    setup_project(host)
    originals = {}
    for directory in (tmp_path, tmp_path / "client_app", host, host / "client_app"):
        directory.mkdir(exist_ok=True)
        path = directory / "package.json"
        originals[path] = (
            json.dumps(
                {
                    "dependencies": {"@simple-module-py/ui": "^0.1.0", "react": "^19"},
                    "devDependencies": {"@simple-module-py/tsconfig": "~0.1.0"},
                    "optionalDependencies": {"@simple-module-py/i18n": "0.1.0"},
                    "peerDependencies": {"@simple-module-py/ui": "^0.1.0"},
                },
                indent="\t",
            )
            + "\n"
        )
        path.write_text(originals[path])
    run_update(tmp_path, dry_run=dry_run, fetcher=registry())
    for path, original in originals.items():
        assert path.read_text() == (original if dry_run else original.replace("0.1.0", "1.2.3"))
    output = capsys.readouterr().out
    assert "17 dependency(ies) across 5 file(s)" in output
    if not dry_run:
        assert "uv sync" in output and "npm install" in output


@pytest.mark.parametrize(
    "pin", ["workspace:*", "file:../ui", "git+https://example/ui", "npm:other@1.0.0", ">=0.1", "*"]
)
def test_npm_unsupported_refs_warn(tmp_path, registry, capsys, pin):
    setup_project(tmp_path)
    path = tmp_path / "package.json"
    original = json.dumps({"dependencies": {"@simple-module-py/ui": pin}})
    path.write_text(original)
    run_update(tmp_path, fetcher=registry())
    assert path.read_text() == original
    output = capsys.readouterr().out
    assert "@simple-module-py/ui: skipped" in output
    assert pin in output


@pytest.mark.parametrize(
    "pin,target,expected",
    [
        ("^9.0.0", "1.2.3", "^9.0.0"),
        ("1.2.3", "1.2.3-rc.1", "1.2.3"),
        ("~1.2.3-rc.2", "1.2.3-rc.1", "~1.2.3-rc.2"),
        ("1.2.3-rc.2", "1.2.3-rc.10", "1.2.3-rc.10"),
        ("^1.2.3-rc.2", "1.2.3", "^1.2.3"),
    ],
)
def test_npm_never_downgrades_including_prereleases(tmp_path, registry, pin, target, expected):
    setup_project(tmp_path)
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"dependencies": {"@simple-module-py/ui": pin}}, indent=4))
    run_update(tmp_path, include_pre=True, fetcher=registry(target))
    assert json.loads(path.read_text())["dependencies"]["@simple-module-py/ui"] == expected
    assert not path.read_text().endswith("\n")


def test_npm_missing_publication_warns(tmp_path, registry, capsys):
    setup_project(tmp_path)
    path = tmp_path / "package.json"
    original = '{"dependencies":{"@simple-module-py/ui":"0.1.0"}}\n'
    path.write_text(original)
    run_update(tmp_path, fetcher=registry(missing=("@simple-module-py/ui",)))
    assert path.read_text() == original
    assert "1.2.3" in capsys.readouterr().out


def test_malformed_json_prevents_all_writes(tmp_path, registry):
    pyproject = setup_project(tmp_path)
    before = pyproject.read_bytes()
    (tmp_path / "package.json").write_text('{"dependencies":{"@simple-module-py/ui":"0.1.0"}}')
    client = tmp_path / "client_app/package.json"
    client.parent.mkdir()
    client.write_text("{bad")
    npm_before = (tmp_path / "package.json").read_bytes()
    with pytest.raises(ValueError):
        run_update(tmp_path, fetcher=registry())
    assert pyproject.read_bytes() == before
    assert (tmp_path / "package.json").read_bytes() == npm_before


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_npm_only_project_uses_core_target_and_preserves_format(tmp_path, registry, newline):
    (tmp_path / "pyproject.toml").write_text('[dependency-groups]\ndev = ["pytest"]\n')
    path = tmp_path / "package.json"
    original = json.dumps({"dependencies": {"@simple-module-py/ui": "0.1.0"}}, indent=3) + "\n"
    original = original.replace("\n", newline)
    path.write_bytes(original.encode())
    run_update(tmp_path, fetcher=registry())
    assert path.read_bytes() == original.replace("0.1.0", "1.2.3").encode()


@pytest.mark.parametrize("missing_core", [False, True])
def test_missing_target_warns_without_npm_writes(tmp_path, capsys, missing_core):
    setup_project(tmp_path)
    path = tmp_path / "package.json"
    original = '{"dependencies":{"@simple-module-py/ui":"0.1.0"}}'
    path.write_text(original)

    def fetch(url):
        if url.startswith("https://pypi.org/"):
            if missing_core:
                raise HTTPError(url, 404, "missing", {}, None)
            return {"releases": {"1.2.3": [{"yanked": False}]}}
        return {"versions": {"1.2.2": {}}}

    run_update(tmp_path, fetcher=fetch)
    assert path.read_text() == original
    output = capsys.readouterr().out
    assert "@simple-module-py/ui: skipped" in output
    assert (
        "simple_module_core not updated" if missing_core else "npm release 1.2.3 unavailable"
    ) in output
    if not missing_core:
        assert "1 dependency(ies) across 1 file(s)" in output


def test_core_prerelease_selection_controls_npm_target(tmp_path, capsys):
    setup_project(tmp_path)
    path = tmp_path / "package.json"
    path.write_text('{"dependencies":{"@simple-module-py/ui":"0.1.0"}}')

    def fetch(url):
        if url.startswith("https://pypi.org/"):
            return {"releases": {"1.2.3": [{"yanked": False}], "2.0.0-rc.1": [{"yanked": False}]}}
        return {"versions": {"1.2.3": {}, "2.0.0-rc.1": {}}}

    run_update(tmp_path, fetcher=fetch)
    assert json.loads(path.read_text())["dependencies"]["@simple-module-py/ui"] == "1.2.3"
    run_update(tmp_path, include_pre=True, fetcher=fetch)
    assert json.loads(path.read_text())["dependencies"]["@simple-module-py/ui"] == "2.0.0-rc.1"


def _client_pin(root, pin="^0.1.0"):
    path = root / "client_app" / "package.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"dependencies": {"@simple-module-py/ui": pin}}) + "\n")
    return path


def test_npm_stays_when_python_core_pin_is_held_back(tmp_path, registry, capsys):
    # An upper bound keeps Python core on 0.1.x; npm must not run ahead of it.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["simple_module_core>=0.1.0,<0.2"]\n'
    )
    pkg = _client_pin(tmp_path)
    run_update(tmp_path, fetcher=registry())
    assert '"^0.1.0"' in pkg.read_text()
    assert "simple_module_core not updated" in capsys.readouterr().out


def test_npm_follows_hyphenated_core_name(tmp_path, registry):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["simple-module-core==0.1.0"]\n'
    )
    pkg = _client_pin(tmp_path)
    run_update(tmp_path, fetcher=registry())
    assert '"^1.2.3"' in pkg.read_text()


@pytest.mark.parametrize("error", [TimeoutError("slow"), ValueError("bad json")])
def test_npm_registry_failure_skips_instead_of_aborting(tmp_path, registry, error, capsys):
    setup_project(tmp_path)
    pkg = _client_pin(tmp_path)
    pypi = registry()

    def fetch(url):
        if url.startswith("https://registry.npmjs.org/"):
            raise error
        return pypi(url)

    run_update(tmp_path, fetcher=fetch)
    assert '"^0.1.0"' in pkg.read_text()
    out = capsys.readouterr().out
    assert "unavailable" in out
    assert "simple_module_core==1.2.3" in (tmp_path / "pyproject.toml").read_text()
