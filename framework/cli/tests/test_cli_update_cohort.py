"""Only distributions released with the framework form its PyPI cohort."""

import tomllib
from pathlib import Path

import pytest
import yaml
from simple_module_cli import pins
from simple_module_cli.package_update import run_update


def test_framework_distributions_match_release_matrix():
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/release.yml").read_text())
    published = workflow["jobs"]["publish-pypi"]["strategy"]["matrix"]["package"]
    assert frozenset(published) == pins.FRAMEWORK_DISTRIBUTIONS


@pytest.mark.parametrize("core_available", [False, True])
def test_named_external_update_leaves_framework_and_other_external_pins_alone(
    tmp_path, fake_pypi, write_pyproject, core_available
):
    project = tmp_path / "pyproject.toml"
    write_pyproject(
        project,
        "simple_module_core==0.0.46",
        "simple_module_images==0.1",
        "simple_module_maps==0.1",
    )
    versions = {"simple_module_images": "0.2", "simple_module_maps": "0.2"}
    if core_available:
        versions["simple_module_core"] = "0.0.47"

    run_update(tmp_path, only="Simple.Module-Images", fetcher=fake_pypi(versions))

    assert tomllib.loads(project.read_text())["project"]["dependencies"] == [
        "simple_module_core==0.0.46",
        "simple_module_images==0.2",
        "simple_module_maps==0.1",
    ]


@pytest.mark.parametrize("external_latest", [None, "2.0"])
def test_external_skip_does_not_block_named_framework_update(
    tmp_path, fake_pypi, write_pyproject, external_latest
):
    project = tmp_path / "pyproject.toml"
    write_pyproject(
        project,
        "simple_module_core==0.0.46",
        "simple_module_db==0.0.46",
        "simple_module_images>=0.1,<1",
    )
    versions = {"simple_module_core": "0.0.47", "simple_module_db": "0.0.47"}
    if external_latest:
        versions["simple_module_images"] = external_latest

    run_update(tmp_path, only="Simple.Module-Core", fetcher=fake_pypi(versions))

    assert tomllib.loads(project.read_text())["project"]["dependencies"] == [
        "simple_module_core==0.0.47",
        "simple_module_db==0.0.47",
        "simple_module_images>=0.1,<1",
    ]


def test_named_external_skip_does_not_reject_a_partial_cohort(tmp_path, fake_pypi, write_pyproject):
    project = tmp_path / "pyproject.toml"
    write_pyproject(project, "simple_module_images>=0.1,<1")
    before = project.read_bytes()

    run_update(
        tmp_path,
        only="simple_module_images",
        fetcher=fake_pypi({"simple_module_images": "2.0"}),
    )

    assert project.read_bytes() == before
