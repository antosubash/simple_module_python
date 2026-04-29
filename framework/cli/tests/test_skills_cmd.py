"""Tests for the ``sm skills`` subcommand group."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from simple_module_cli import skills_cmd
from simple_module_cli.cli import app as root_app
from typer.testing import CliRunner


@pytest.fixture
def fake_skills_root(tmp_path, monkeypatch):
    """Create a tiny bundled-skills directory and route the CLI at it."""
    root = tmp_path / "bundled"
    root.mkdir()

    (root / "alpha").mkdir()
    (root / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: First fake skill for testing.\n---\n\n# Alpha\n",
        encoding="utf-8",
    )

    (root / "beta").mkdir()
    (root / "beta" / "SKILL.md").write_text(
        "---\n"
        "name: beta\n"
        "description: Second fake skill, with a multi-line\n"
        "  description that spans lines.\n"
        "---\n\n"
        "# Beta\n",
        encoding="utf-8",
    )
    (root / "beta" / "scripts").mkdir()
    (root / "beta" / "scripts" / "helper.py").write_text("print('hi')\n", encoding="utf-8")

    # A junk dir without a SKILL.md must be ignored.
    (root / "not-a-skill").mkdir()

    monkeypatch.setattr(skills_cmd, "_bundled_skills_root", lambda: root)
    return root


class TestIterBundledSkills:
    def test_lists_only_dirs_with_skill_md(self, fake_skills_root):
        skills = skills_cmd.iter_bundled_skills()
        names = [p.name for p in skills]
        assert names == ["alpha", "beta"]

    def test_returns_empty_when_root_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "nope"
        monkeypatch.setattr(skills_cmd, "_bundled_skills_root", lambda: missing)
        assert skills_cmd.iter_bundled_skills() == []


class TestList:
    def test_prints_each_bundled_skill(self, fake_skills_root):
        runner = CliRunner()
        result = runner.invoke(root_app, ["skills", "list"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "First fake skill" in result.output
        assert "beta" in result.output

    def test_empty_bundle_is_handled(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(skills_cmd, "_bundled_skills_root", lambda: empty)
        runner = CliRunner()
        result = runner.invoke(root_app, ["skills", "list"])
        assert result.exit_code == 0
        assert "no skills bundled" in result.output


class TestAdd:
    def test_installs_all_skills_when_no_args(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        target = tmp_path / "project"
        target.mkdir()
        result = runner.invoke(
            root_app,
            ["skills", "add", "--dest", str(target / ".claude" / "skills")],
        )
        assert result.exit_code == 0, result.output
        assert (target / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()
        assert (target / ".claude" / "skills" / "beta" / "SKILL.md").is_file()
        # Subdirectories of the source skill copy through too.
        assert (target / ".claude" / "skills" / "beta" / "scripts" / "helper.py").is_file()

    def test_installs_only_named_skills(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        dest = tmp_path / "x"
        result = runner.invoke(root_app, ["skills", "add", "alpha", "--dest", str(dest)])
        assert result.exit_code == 0, result.output
        assert (dest / "alpha" / "SKILL.md").is_file()
        assert not (dest / "beta").exists()

    def test_unknown_skill_errors_with_listing(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            root_app,
            ["skills", "add", "ghost", "--dest", str(tmp_path / "x")],
        )
        assert result.exit_code == 1
        assert "unknown skill" in result.output.lower()
        assert "alpha" in result.output and "beta" in result.output

    def test_skips_existing_without_force(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        dest = tmp_path / "x"
        runner.invoke(root_app, ["skills", "add", "alpha", "--dest", str(dest)])
        # Sentinel file inside the existing skill must survive the second run.
        sentinel = dest / "alpha" / "user-edit.md"
        sentinel.write_text("hand-edited", encoding="utf-8")

        result = runner.invoke(root_app, ["skills", "add", "alpha", "--dest", str(dest)])
        assert result.exit_code == 0, result.output
        assert "skipped" in result.output
        assert sentinel.read_text(encoding="utf-8") == "hand-edited"

    def test_force_overwrites(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        dest = tmp_path / "x"
        runner.invoke(root_app, ["skills", "add", "alpha", "--dest", str(dest)])
        sentinel = dest / "alpha" / "user-edit.md"
        sentinel.write_text("hand-edited", encoding="utf-8")

        result = runner.invoke(root_app, ["skills", "add", "alpha", "--dest", str(dest), "--force"])
        assert result.exit_code == 0, result.output
        assert "updated" in result.output
        # --force replaces the directory wholesale, so the sentinel goes away.
        assert not sentinel.exists()
        assert (dest / "alpha" / "SKILL.md").is_file()

    def test_symlink_creates_link(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        dest = tmp_path / "x"
        result = runner.invoke(
            root_app,
            ["skills", "add", "alpha", "--dest", str(dest), "--symlink"],
        )
        assert result.exit_code == 0, result.output
        installed = dest / "alpha"
        assert installed.is_symlink()
        assert installed.resolve() == (fake_skills_root / "alpha").resolve()

    def test_global_flag_writes_under_home_claude(self, fake_skills_root, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
        # Re-evaluate the module-level constant against the patched home.
        monkeypatch.setattr(skills_cmd, "_GLOBAL_DIR", fake_home / ".claude" / "skills")

        runner = CliRunner()
        result = runner.invoke(root_app, ["skills", "add", "alpha", "-g"])
        assert result.exit_code == 0, result.output
        assert (fake_home / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()


class TestUpdate:
    def test_updates_only_already_installed_when_no_names(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        dest = tmp_path / "x"
        # Pre-install just alpha, then call update with no names — beta must
        # stay un-installed because it wasn't there before.
        runner.invoke(root_app, ["skills", "add", "alpha", "--dest", str(dest)])

        # Hand-edit alpha so we can prove the update overwrites.
        (dest / "alpha" / "edit.md").write_text("e", encoding="utf-8")

        result = runner.invoke(root_app, ["skills", "update", "--dest", str(dest)])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "beta" not in result.output
        assert not (dest / "beta").exists()
        # alpha was force-replaced, so the hand-edited file is gone.
        assert not (dest / "alpha" / "edit.md").exists()

    def test_explicit_names_force_install_even_if_missing(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        dest = tmp_path / "x"
        # beta isn't installed yet; update with explicit name should still install it.
        result = runner.invoke(root_app, ["skills", "update", "beta", "--dest", str(dest)])
        assert result.exit_code == 0, result.output
        assert (dest / "beta" / "SKILL.md").is_file()

    def test_no_dest_dir_yields_friendly_message(self, fake_skills_root, tmp_path):
        runner = CliRunner()
        missing = tmp_path / "never-created"
        result = runner.invoke(root_app, ["skills", "update", "--dest", str(missing)])
        assert result.exit_code == 0
        assert "Nothing to update" in result.output


class TestSkillsRegisteredOnRootApp:
    def test_skills_subcommand_visible_in_help(self):
        runner = CliRunner()
        result = runner.invoke(root_app, ["--help"])
        assert result.exit_code == 0, result.output
        assert "skills" in result.output


class TestRealBundle:
    """Smoke test: the actual skills shipped with this CLI are discoverable."""

    def test_bundled_skills_root_exists(self):
        # Editable install: simple_module_cli/skills is a symlink into repo /skills.
        # Wheel install: shared-data force-include copies the dir verbatim.
        # Either way, the root must exist and contain at least the two original skills.
        root = skills_cmd._bundled_skills_root()
        assert root.is_dir(), f"bundled skills root missing: {root}"
        names = {p.name for p in skills_cmd.iter_bundled_skills(root)}
        assert "simple-module-creating" in names
        assert "simple-module-cli" in names

    def test_every_bundled_skill_has_valid_frontmatter(self):
        for skill in skills_cmd.iter_bundled_skills():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            assert text.startswith("---\n"), f"{skill.name}: missing frontmatter"
            # Frontmatter must declare both name + description.
            head = text.split("---", 2)[1]
            assert "name:" in head, f"{skill.name}: frontmatter has no name"
            assert "description:" in head, f"{skill.name}: frontmatter has no description"


def test_typer_app_exports() -> None:
    """The skills subcommand exports a Typer instance — required for add_typer."""
    assert isinstance(skills_cmd.app, typer.Typer)
