"""SM022/SM023 — module CSS placed in the wrong file.

The theme.css / styles.css split is what makes the cascade rules structural
rather than merely documented, so putting a construct in the wrong file
produces surprising-but-legal CSS. Both codes are warnings for that reason:
the build succeeds either way.
"""

from __future__ import annotations


def _mod():
    from simple_module_core import ModuleBase, ModuleMeta

    class Styled(ModuleBase):
        meta = ModuleMeta(name="Styled")

    return Styled()


class TestSm022ThemeConstructsInStylesCss:
    def test_theme_at_rule_in_styles_css(self, tmp_path):
        """@theme inside styles.css is inert — styles.css is imported layered."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("@theme {\n  --color-x: red;\n}\n")

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM022"]
        assert diags[0].level.value == "warning"

    def test_custom_variant_in_styles_css(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("@custom-variant dark (&:where(.dark, .dark *));\n")

        assert [d.code for d in check_module_css(_mod(), tmp_path)] == ["SM022"]

    def test_utility_at_rule_in_styles_css(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("@utility tab-4 {\n  tab-size: 4;\n}\n")

        assert [d.code for d in check_module_css(_mod(), tmp_path)] == ["SM022"]

    def test_reports_the_offending_line(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            "@layer components {\n  .x { color: red; }\n}\n\n@theme {\n  --a: 1;\n}\n"
        )

        diags = check_module_css(_mod(), tmp_path)

        assert len(diags) == 1
        # Line number rides in `file` as path:line, matching _inertia_api.py.
        assert diags[0].file.endswith("styles.css:5")


class TestSm023UnlayeredRulesInThemeCss:
    def test_plain_rule_in_theme_css(self, tmp_path):
        """An unlayered rule in theme.css outranks every Tailwind utility."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(".card {\n  padding: 0;\n}\n")

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM023"]
        assert diags[0].level.value == "warning"

    def test_root_block_allowed(self, tmp_path):
        """:root custom-property blocks are legitimate in theme.css."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text("@theme {\n  --a: 1;\n}\n:root {\n  --b: 2;\n}\n")

        assert check_module_css(_mod(), tmp_path) == []

    def test_root_variants_allowed(self, tmp_path):
        """Dark-mode token blocks keyed off :root are the normal pattern."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(':root,\n:root[data-theme="dark"] {\n  --b: 2;\n}\n')

        assert check_module_css(_mod(), tmp_path) == []

    def test_font_face_allowed(self, tmp_path):
        """@font-face is explicitly part of what theme.css is for."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(
            "@font-face {\n  font-family: X;\n  src: url(x.woff2);\n}\n"
        )

        assert check_module_css(_mod(), tmp_path) == []


class TestScannerRobustness:
    def test_nested_at_rule_not_flagged(self, tmp_path):
        """Only top-level constructs count — brace depth is tracked."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("@layer components {\n  .x { color: red; }\n}\n")

        assert check_module_css(_mod(), tmp_path) == []

    def test_nested_rule_in_theme_css_not_flagged(self, tmp_path):
        """A rule nested inside @theme is not a top-level rule."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text("@theme {\n  --a: 1;\n}\n")

        assert check_module_css(_mod(), tmp_path) == []

    def test_comments_stripped_before_scanning(self, tmp_path):
        """A commented-out @theme is not a finding."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("/* @theme { --x: 1; } */\n.y { color: red; }\n")

        assert check_module_css(_mod(), tmp_path) == []

    def test_comment_does_not_shift_line_numbers(self, tmp_path):
        """Stripping comments must preserve newlines, or line numbers drift."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("/* a\n   multi-line\n   comment */\n@theme {\n}\n")

        diags = check_module_css(_mod(), tmp_path)

        assert [d.file.rsplit(":", 1)[1] for d in diags] == ["4"]

    def test_clean_module_has_no_findings(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text("@theme {\n  --color-x: red;\n}\n")
        (tmp_path / "styles.css").write_text("@layer components {\n  .x { color: red; }\n}\n")

        assert check_module_css(_mod(), tmp_path) == []

    def test_missing_files_are_not_findings(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        assert check_module_css(_mod(), tmp_path) == []

    def test_import_statement_allowed_in_either_file(self, tmp_path):
        """A statement at-rule ending in ; is not a rule block."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text('@import "other.css";\n')
        (tmp_path / "styles.css").write_text('@charset "utf-8";\n')

        assert check_module_css(_mod(), tmp_path) == []
