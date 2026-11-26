from simple_module_remote.output.sanitize import sanitize


def test_strips_escapes_and_controls_keeps_newline_tab():
    text = "a\x1b[1;31mb\x1b]8;;http://x\x07c\x1b]0;t\x1b\\d\x00\x7f\x85\te\n"
    assert sanitize(text) == "abcd\te\n"


def test_lone_escape_removed():
    assert sanitize("x\x1b") == "x"


def test_strips_bidi_overrides_and_line_separators():
    assert sanitize("a\u202eb\u2066c\u2069d\u2028e\u2029f") == "abcdef"
