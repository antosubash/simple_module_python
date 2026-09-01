"""Constraint rewriting for `smpy package-update` — GH #284.

Split from `test_cli_package_update.py` (which covers file walking, workspace
members and the PyPI lookup) to keep both under the 300-line cap.

The rule under test throughout: bumping a dependency changes its *version*,
not its *pin style*, and never silently drops a bound that excludes the
release being installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_cli import package_update as pu


def test_exact_pins_stay_exact(tmp_path: Path, fake_pypi, write_pyproject) -> None:
    """The #284 regression: `package-update` bumped versions *and* pin style."""
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "simple_module_core==0.0.32", "simple_module_db===0.0.32")

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "0.0.33", "simple_module_db": "0.0.33"}),
    )

    out = pyproject.read_text(encoding="utf-8")
    assert "simple_module_core==0.0.33" in out
    assert "simple_module_db===0.0.33" in out
    assert ">=" not in out


def test_compatible_release_pin_stays_compatible(
    tmp_path: Path, fake_pypi, write_pyproject
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "simple_module_core~=0.0.32")

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "0.0.33"}),
    )

    assert "simple_module_core~=0.0.33" in pyproject.read_text(encoding="utf-8")


def test_loosen_flag_restores_the_old_rewrite(tmp_path: Path, fake_pypi, write_pyproject) -> None:
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "simple_module_core==0.0.32")

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        loosen=True,
        fetcher=fake_pypi({"simple_module_core": "0.0.33"}),
    )

    assert "simple_module_core>=0.0.33" in pyproject.read_text(encoding="utf-8")


def test_unconstrained_dep_gets_a_lower_bound(tmp_path: Path, fake_pypi, write_pyproject) -> None:
    """Nothing to preserve, so the tool's default style applies."""
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "simple_module_core")

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "0.0.33"}),
    )

    assert "simple_module_core>=0.0.33" in pyproject.read_text(encoding="utf-8")


def test_upper_bound_excluding_latest_skips_rather_than_drops(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fake_pypi, write_pyproject
) -> None:
    """The old rewrite silently deleted the ceiling; now it's reported."""
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "simple_module_core>=0.1,<1.0")

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "2.0.0"}),
    )

    assert "simple_module_core>=0.1,<1.0" in pyproject.read_text(encoding="utf-8")
    assert "excluded by <1.0" in capsys.readouterr().out


def test_extras_and_markers_survive_the_rewrite(tmp_path: Path, fake_pypi, write_pyproject) -> None:
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "simple_module_core[redis]==0.0.32; python_version >= '3.12'")

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "0.0.33"}),
    )

    out = pyproject.read_text(encoding="utf-8")
    assert "simple_module_core[redis]==0.0.33" in out
    assert "python_version >= '3.12'" in out


class TestWildcardsAndImplicitCeilings:
    """Wildcards and `~=` carry ceilings `version_key` can't see.

    `version_key` maps `*` to 0, so `!=1.0.*` compared numerically reads as
    `!=1.0.0` and never fires. That produced `>=1.0.5,!=1.0.*` — a specifier
    nothing can satisfy, which fails the `uv sync` the tool tells you to run.
    """

    def test_wildcard_exclusion_is_honoured(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core>=1.0,!=1.0.*")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "1.0.5"}),
        )

        assert "simple_module_core>=1.0,!=1.0.*" in pyproject.read_text(encoding="utf-8")

    def test_wildcard_that_does_not_cover_latest_still_bumps(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        """`!=1.1.*` has nothing to say about 1.0.5, so the floor moves."""
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core>=1.0,!=1.1.*")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "1.0.5"}),
        )

        assert "simple_module_core>=1.0.5,!=1.1.*" in pyproject.read_text(encoding="utf-8")

    def test_compatible_release_outside_its_band_is_reported(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        """`~=1.4` means `>=1.4, ==1.*`, so 2.0.0 is out of range."""
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core~=1.4")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "2.0.0"}),
        )

        assert "simple_module_core~=1.4" in pyproject.read_text(encoding="utf-8")
        assert "~=2.0.0" not in pyproject.read_text(encoding="utf-8")

    def test_compatible_release_inside_its_band_moves(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core~=1.4.2")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "1.4.9"}),
        )

        assert "simple_module_core~=1.4.9" in pyproject.read_text(encoding="utf-8")

    def test_wildcard_pin_covering_latest_is_left_alone(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        """`==1.0.*` already allows 1.0.5; narrowing it would change policy."""
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core==1.0.*")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "1.0.5"}),
        )

        assert "simple_module_core==1.0.*" in pyproject.read_text(encoding="utf-8")

    def test_wildcard_pin_not_covering_latest_is_reported(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core==1.0.*")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "1.1.0"}),
        )

        assert "simple_module_core==1.0.*" in pyproject.read_text(encoding="utf-8")


class TestNeverDowngrades:
    """PyPI's latest can be *older* than what the project already asks for.

    The workspace bumps its own pins ahead of the release (every module here
    pins `simple_module_core==<next>` before that version is published), so a
    `package-update` run in that window must not rewrite the pin backwards —
    with exact pins preserved, `==0.0.33` → `==0.0.32` is a real downgrade the
    following `uv sync` would install.
    """

    def test_an_exact_pin_ahead_of_pypi_is_left_alone(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core==0.0.33")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "0.0.32"}),
        )

        assert "simple_module_core==0.0.33" in pyproject.read_text(encoding="utf-8")

    def test_a_floor_ahead_of_pypi_is_left_alone(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core>=0.0.33")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "0.0.32"}),
        )

        assert "simple_module_core>=0.0.33" in pyproject.read_text(encoding="utf-8")

    def test_compatible_release_keeps_its_band_width(
        self, tmp_path: Path, fake_pypi, write_pyproject
    ) -> None:
        """`~=1.4` means `==1.*`; `~=1.5.0` would mean `==1.5.*`.

        Narrowing it is a pin-style change, and it freezes the dependency: the
        next run would report 1.6.0 as "excluded by ~=1.5.0".
        """
        pyproject = tmp_path / "pyproject.toml"
        write_pyproject(pyproject, "simple_module_core~=1.4")

        pu.run_update(
            path=pyproject,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({"simple_module_core": "1.5.0"}),
        )

        assert "simple_module_core~=1.5" in pyproject.read_text(encoding="utf-8")
        assert "~=1.5.0" not in pyproject.read_text(encoding="utf-8")
