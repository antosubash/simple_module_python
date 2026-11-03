"""Manifest-level release ordering regressions for GH #766."""

import tomllib
from pathlib import Path

import pytest
from simple_module_cli.package_update import run_update


@pytest.mark.parametrize(
    ("current", "releases", "include_pre", "expected"),
    [
        ("0.0.42", ["0.0.43rc1", "0.0.43rc2"], True, "0.0.43rc2"),
        ("0.0.42", ["0.0.43rc2", "0.0.43"], True, "0.0.43"),
        ("0.0.43rc1", ["0.0.43"], False, "0.0.43"),
        ("0.0.42", ["0.0.43"], False, "0.0.43"),
        ("0.0.43rc2", ["0.0.43rc1"], True, "0.0.43rc2"),
        ("0.0.43", ["0.0.43rc2"], True, "0.0.43"),
        ("0.0.44rc1", ["0.0.43"], False, "0.0.44rc1"),
        ("0.0.42", ["999.invalid", "0.0.43"], True, "0.0.43"),
    ],
    ids=[
        "rc-progression",
        "final-over-rc",
        "rc-to-final",
        "stable-control",
        "no-older-rc",
        "no-final-to-rc",
        "no-older-stable",
        "invalid-release",
    ],
)
def test_package_update_orders_releases(
    tmp_path: Path,
    write_pyproject,
    current: str,
    releases: list[str],
    include_pre: bool,
    expected: str,
) -> None:
    manifest = tmp_path / "pyproject.toml"
    write_pyproject(manifest, f"simple_module_core=={current}")

    def fetcher(url: str) -> dict:
        return {"releases": {v: [{"yanked": False}] for v in releases}}

    run_update(manifest, include_pre=include_pre, fetcher=fetcher)

    assert tomllib.loads(manifest.read_text())["project"]["dependencies"] == [
        f"simple_module_core=={expected}"
    ]


@pytest.mark.parametrize(
    ("bound", "expected"),
    [
        ("<0.0.43", "0.0.42"),
        ("<=0.0.43", "0.0.43rc2"),
        ("!=0.0.43", "0.0.43rc2"),
    ],
)
def test_package_update_checks_prerelease_bounds(
    tmp_path: Path, write_pyproject, fake_pypi, bound: str, expected: str
) -> None:
    manifest = tmp_path / "pyproject.toml"
    write_pyproject(manifest, f"simple_module_core>=0.0.42,{bound}")

    run_update(manifest, include_pre=True, fetcher=fake_pypi({"simple_module_core": "0.0.43rc2"}))

    assert tomllib.loads(manifest.read_text())["project"]["dependencies"] == [
        f"simple_module_core>={expected},{bound}"
    ]


@pytest.mark.parametrize(
    "spec",
    ["a==foo", "a>=1.x", "a<foo", "a!=foo", "a===foo", "a~=1.x", "a<1.0+local", "a<=1.0+local"],
)
def test_rewrite_skips_unorderable_pins(spec: str) -> None:
    from simple_module_cli.requirements import rewrite_requirement

    result = rewrite_requirement(spec, "1.2.3")
    assert result.spec is None
    assert result.reason and "unsupported version spelling" in result.reason


def test_compatible_floor_does_not_jump_past_a_prerelease() -> None:
    from simple_module_cli.requirements import rewrite_requirement

    # ``1.5.0rc1`` truncated to the pin's width is ``1.5``, above the rc itself.
    assert rewrite_requirement("simple_module_core~=1.4", "1.5.0rc1").spec is None
    # At full width the rc is a valid floor and still satisfies the band.
    result = rewrite_requirement("simple_module_core~=1.4.2", "1.4.3rc1")
    assert result.spec == "simple_module_core~=1.4.3rc1"
