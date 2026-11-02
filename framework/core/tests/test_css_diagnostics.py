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
