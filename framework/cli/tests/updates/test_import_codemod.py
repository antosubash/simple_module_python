from __future__ import annotations

import textwrap
from pathlib import Path

from simple_module_cli.cli import app
from simple_module_cli.updates.import_codemod import load_renames, resolve, rewrite_source
from typer.testing import CliRunner

RENAMES = {
    "simple_module_core.cors": "simple_module_core.web.cors",
    "simple_module_core.migration_support": "simple_module_core.migrations.support",
    "simple_module_db.deps": "simple_module_db.engine.deps",
}


def _rewrite(source: str) -> str:
    return rewrite_source(textwrap.dedent(source), RENAMES).source


def test_shipped_table_loads_and_points_inside_the_framework() -> None:
    renames = load_renames()
    assert len(renames) > 100
    assert all(old.split(".")[0] == new.split(".")[0] for old, new in renames.items())


def test_resolve_matches_exact_and_package_prefix() -> None:
    assert resolve("simple_module_core.cors", RENAMES) == "simple_module_core.web.cors"
    assert (
        resolve("simple_module_core.migration_support.x", RENAMES)
        == "simple_module_core.migrations.support.x"
    )
    assert resolve("simple_module_core.corsair", RENAMES) is None


def test_from_import_keeps_names_and_comments() -> None:
    out = _rewrite(
        """\
        from simple_module_core.cors import (  # keep
            CorsPolicy,
            CorsRegistry as Reg,
        )
        """
    )
    assert out.startswith("from simple_module_core.web.cors import (  # keep\n")
    assert "CorsRegistry as Reg," in out


def test_plain_import_rewrites_attribute_chains() -> None:
    out = _rewrite(
        """\
        import simple_module_db.deps

        dep = simple_module_db.deps.get_db
        """
    )
    assert "import simple_module_db.engine.deps\n" in out
    assert "dep = simple_module_db.engine.deps.get_db" in out


def test_aliased_import_leaves_usages_alone() -> None:
    out = _rewrite("import simple_module_db.deps as deps\nx = deps.get_db\n")
    assert out == "import simple_module_db.engine.deps as deps\nx = deps.get_db\n"


def test_from_package_import_module_is_split_and_aliased() -> None:
    out = _rewrite(
        """\
        def f():
            from simple_module_core import Services, cors, migration_support
        """
    )
    assert out == textwrap.dedent(
        """\
        def f():
            from simple_module_core import Services
            from simple_module_core.web import cors
            from simple_module_core.migrations import support as migration_support
        """
    )


def test_dotted_strings_are_rewritten() -> None:
    out = _rewrite('patch("simple_module_core.cors.CorsRegistry")\nx = "simple_module_core"\n')
    assert out == 'patch("simple_module_core.web.cors.CorsRegistry")\nx = "simple_module_core"\n'


def test_unsafe_statements_are_reported_not_rewritten() -> None:
    source = "import os; from simple_module_core import cors\n"
    result = rewrite_source(source, RENAMES)
    assert result.source == source
    assert result.manual == ["line 1: from simple_module_core import ..."]


def test_non_ascii_source_keeps_byte_offsets_right() -> None:
    out = _rewrite('s = "héllo"; import simple_module_db.deps as d\n')
    assert out == 's = "héllo"; import simple_module_db.engine.deps as d\n'


def test_syntax_error_is_reported() -> None:
    result = rewrite_source("def (:\n", RENAMES)
    assert not result.changed
    assert result.manual[0].startswith("not parsed")


def test_relative_and_unrelated_imports_are_untouched() -> None:
    source = "from . import cors\nfrom .cors import x\nimport simple_module_core\n"
    assert _rewrite(source) == source


def test_cli_check_diff_and_write(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    (app_dir / ".venv").mkdir(parents=True)
    target = app_dir / "orders.py"
    target.write_text("from simple_module_core.cors import CorsRegistry\n", encoding="utf-8")
    (app_dir / ".venv" / "skip.py").write_text("import simple_module_core.cors\n", encoding="utf-8")
    runner = CliRunner()

    checked = runner.invoke(app, ["fix-imports", "--check", str(app_dir)])
    assert checked.exit_code == 1
    assert "1 file(s) would change" in checked.output

    diffed = runner.invoke(app, ["fix-imports", "--diff", str(app_dir)])
    assert "+from simple_module_core.web.cors import CorsRegistry" in diffed.output
    assert target.read_text(encoding="utf-8").startswith("from simple_module_core.cors")

    written = runner.invoke(app, ["fix-imports", str(app_dir)])
    assert written.exit_code == 0
    assert target.read_text(encoding="utf-8") == (
        "from simple_module_core.web.cors import CorsRegistry\n"
    )
    assert runner.invoke(app, ["fix-imports", "--check", str(app_dir)]).exit_code == 0
