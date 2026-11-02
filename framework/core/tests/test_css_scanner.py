"""The CSS scanner behind SM022/SM023.

`check_module_css` is only as good as its ability to find *top-level*
constructs, and it does that with a hand-rolled brace-depth scan rather than a
CSS parse — no parser joins the runtime dependencies to power a lint. These
tests pin the tokenising rules that scan depends on: comments, quoted strings,
escapes, and the line numbers reported alongside a finding.

Every case here is a bug that shipped at some point during review: each one is
a way a stray character silently desynced the depth counter and made the lint
stop reporting anything at all.
"""

from __future__ import annotations


def _mod():
    from simple_module_core import ModuleBase, ModuleMeta

    class Styled(ModuleBase):
        meta = ModuleMeta(name="Styled")

    return Styled()


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

    def test_commented_out_construct_is_not_a_finding(self, tmp_path):
        """A commented-out @theme is not a finding."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("/* @theme { --x: 1; } */\n.y { color: red; }\n")

        assert check_module_css(_mod(), tmp_path) == []

    def test_comment_does_not_shift_line_numbers(self, tmp_path):
        """Newlines inside a skipped comment must still be counted."""
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

    def test_open_brace_in_a_string_does_not_hide_later_findings(self, tmp_path):
        """A brace inside a string must not desync the depth counter.

        An icon-font rule like `content: "{"` used to leave the scanner
        permanently one level deep, so every later top-level construct read as
        nested — silently swallowing the very @theme SM022 exists to catch.
        """
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text('.icon { content: "{"; }\n@theme {\n  --a: 1;\n}\n')

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM022"]
        assert diags[0].file.endswith("styles.css:2")

    def test_close_brace_in_a_string_is_not_a_finding(self, tmp_path):
        """A closing brace inside a string must not end the block early."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(':root {\n  --icon-close: "}";\n}\n')

        assert check_module_css(_mod(), tmp_path) == []

    def test_escaped_quote_in_a_string(self, tmp_path):
        """A backslash-escaped quote does not terminate the string."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(':root {\n  --q: "a\\"{b";\n}\n')

        assert check_module_css(_mod(), tmp_path) == []

    def test_single_quoted_strings_handled(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            ".icon { content: '{'; }\n@utility tab-4 {\n  tab-size: 4;\n}\n"
        )

        assert [d.code for d in check_module_css(_mod(), tmp_path)] == ["SM022"]

    def test_unterminated_string_does_not_swallow_the_file(self, tmp_path):
        """A stray quote must not disable the lint for everything after it.

        A CSS string cannot contain a raw newline, so an unterminated one ends
        at end-of-line. Without that bound, a single typo'd quote left the
        scanner permanently "inside a string" and every later brace stopped
        counting — silently hiding the rest of the file's findings.
        """
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            '.a { color: red; }\n.b {\n  content: "unterminated;\n}\n@theme {\n  --b: 1;\n}\n'
        )

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM022"]
        assert diags[0].file.endswith("styles.css:5")

    def test_apostrophe_in_unquoted_url_does_not_swallow_the_file(self, tmp_path):
        """An unquoted url() token may hold a lone apostrophe, e.g. inline SVG."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            ".icon {\n"
            "  background: url(data:image/svg+xml,<text>it's here</text>);\n"
            "}\n"
            "@theme {\n"
            "  --a: 1;\n"
            "}\n"
        )

        assert [d.code for d in check_module_css(_mod(), tmp_path)] == ["SM022"]

    def test_stray_quote_does_not_eat_a_brace_on_its_own_line(self, tmp_path):
        """The unmatched-quote case, with the closing brace on the SAME line.

        Bounding strings at newlines was not enough: the `}` here sits on the
        stray quote's own line, so it was consumed as string content and the
        depth counter stayed desynced for the rest of the file. A quote only
        opens a string if its partner appears before the line ends.
        """
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            ".icon { background: url(it's.png); }\n@theme {\n  --a: 1;\n}\n"
        )

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM022"]
        assert diags[0].file.endswith("styles.css:2")

    def test_multiline_quoted_value_is_not_a_finding(self, tmp_path):
        """grid-template-areas spreads several complete strings over lines."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            "@layer components {\n"
            "  .g {\n"
            "    grid-template-areas:\n"
            '      "a b"\n'
            '      "c d";\n'
            "  }\n"
            "}\n"
        )

        assert check_module_css(_mod(), tmp_path) == []

    def test_escaped_selector_is_not_a_string_opener(self, tmp_path):
        """CSS escapes apply outside strings — Tailwind selectors rely on it."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            ".mt-\\[773px\\] { margin-top: 773px; }\n@theme {\n  --a: 1;\n}\n"
        )

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM022"]
        assert diags[0].file.endswith("styles.css:2")

    def test_scanner_is_linear_on_pathological_input(self, tmp_path):
        """A long run of escaped quotes must not make the scan quadratic.

        `doctor` runs this over every installed module, including third-party
        ones, so a minified or vendored stylesheet must not stall the lint.
        Before escapes were consumed outside strings, 58KB of `\\'` took ~10s.
        """
        import time

        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("\\'" * 60_000)

        started = time.perf_counter()
        check_module_css(_mod(), tmp_path)
        elapsed = time.perf_counter() - started

        assert elapsed < 2.0, f"scan took {elapsed:.1f}s — likely quadratic again"

    def test_escaped_newline_continues_a_string(self, tmp_path):
        """A backslash-escaped newline is the one way a string spans lines."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(':root {\n  --a: "x\\\n  y";\n}\n')

        assert check_module_css(_mod(), tmp_path) == []

    def test_brace_inside_a_comment_is_not_structural(self, tmp_path):
        """An unbalanced brace in a comment must not shift depth either."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("/* } { */\n@theme {\n  --a: 1;\n}\n")

        diags = check_module_css(_mod(), tmp_path)

        assert [d.code for d in diags] == ["SM022"]
        assert diags[0].file.endswith("styles.css:2")

    def test_import_statement_allowed_in_either_file(self, tmp_path):
        """A statement at-rule ending in ; is not a rule block."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text('@import "other.css";\n')
        (tmp_path / "styles.css").write_text('@charset "utf-8";\n')

        assert check_module_css(_mod(), tmp_path) == []
