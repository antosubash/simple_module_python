"""SM022/SM023: module CSS placed in the file with the wrong cascade position.

A module ships its styles in two files, and which one a construct lands in
decides how it cascades:

* ``theme.css`` is imported **unlayered**, because a ``@theme`` block inside a
  cascade layer registers no design tokens at all. Unlayered CSS also outranks
  every layered rule, so a plain rule here would beat any Tailwind utility.
* ``styles.css`` is imported into ``layer(components)``, so its rules always
  lose to a utility — which is what you want for component CSS, and useless
  for ``@theme``.

Both codes are warnings, not errors: the misplaced CSS is legal and builds
fine, it just cascades in a way the author almost certainly did not intend.

Detection is a line-oriented scan that tracks brace depth, not a CSS parse —
adding a CSS parser as a runtime dependency to power a lint is not worth it.
This catches the ordinary mistake of putting a construct in the wrong file; it
is not a conformance checker, and pathological input (an at-rule assembled by
preprocessing, say) is out of scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

THEME_CSS = "theme.css"
STYLES_CSS = "styles.css"

# Constructs that only do anything unlayered, so they belong in theme.css.
THEME_ONLY_AT_RULES = ("@theme", "@custom-variant", "@utility")


def _top_level_preludes(text: str) -> list[tuple[str, int]]:
    """Return ``(prelude, line_number)`` for every top-level construct.

    A "prelude" is the selector or at-rule text preceding a top-level ``{``,
    or a whole statement at-rule terminated by ``;`` at depth 0. Anything
    nested inside braces is skipped, which is what keeps a rule inside
    ``@layer components { ... }`` from being mistaken for a top-level one.

    Comments and quoted strings are consumed inline rather than pre-stripped,
    because a brace inside either is not structural. ``content: "{"`` in an
    icon-font rule would otherwise desynchronise the depth counter for the
    whole rest of the file — every later top-level construct would be read as
    nested and silently skipped.

    A quote only opens a string when its partner is found before the line
    ends, which is the rule CSS itself applies (a string cannot contain a raw
    newline). Treating every quote as an opener is what makes an *unmatched*
    one dangerous: the lone apostrophe in ``url(it's.png); }`` would swallow
    the closing brace on that same line and desync the counter permanently.
    An unmatched quote is therefore just an ordinary character.
    """
    out: list[tuple[str, int]] = []
    depth = 0
    buf: list[str] = []
    line = 1
    buf_line = 1
    i = 0
    n = len(text)

    def flush() -> None:
        prelude = "".join(buf).strip()
        if prelude:
            out.append((prelude, buf_line))

    def string_end(start: int, quote: str) -> int | None:
        """Index just past the closing quote, or None if it never closes."""
        j = start + 1
        while j < n:
            c = text[j]
            if c == "\\":
                # An escape consumes the next character whole — including a
                # newline, the one way a CSS string legitimately spans lines.
                j += 2
                continue
            if c == "\n":
                return None
            if c == quote:
                return j + 1
            j += 1
        return None

    while i < n:
        ch = text[i]

        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            line += text.count("\n", i, end)
            i = end
            continue

        if ch == "\\" and i + 1 < n:
            # CSS escapes apply outside strings too — Tailwind leans on this
            # heavily (`.mt-\[773px\]`). Consuming the pair keeps an escaped
            # quote from being mistaken for a string opener, which is also
            # what stops `\'` repeated across a long line from making
            # string_end re-scan that line once per quote (quadratic).
            if depth == 0:
                if not buf:
                    buf_line = line
                buf.append(text[i : i + 2])
            if text[i + 1] == "\n":
                line += 1
            i += 2
            continue

        if ch in "\"'":
            end = string_end(i, ch)
            if end is not None:
                if depth == 0:
                    if not buf:
                        buf_line = line
                    buf.append(text[i:end])
                line += text.count("\n", i, end)
                i = end
                continue
            # Unmatched: fall through and treat it as an ordinary character.

        if ch == "{":
            if depth == 0:
                flush()
                buf.clear()
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                buf.clear()
        elif depth == 0:
            if ch == ";":
                flush()
                buf.clear()
            elif buf:
                buf.append(ch)
            elif not ch.isspace():
                # Start the buffer at the first non-space character, so
                # buf_line points at the construct rather than at whatever
                # blank lines preceded it.
                buf_line = line
                buf.append(ch)

        if ch == "\n":
            line += 1
        i += 1
    return out


def _is_root_selector(prelude: str) -> bool:
    """True if every comma-separated part of the selector is :root-based.

    ``:root``, ``:root[data-theme="dark"]`` and a comma-separated list of both
    are the normal way to declare design tokens, so they are legitimate in
    theme.css even though they are plain rules.
    """
    parts = [p.strip() for p in prelude.split(",") if p.strip()]
    return bool(parts) and all(p.startswith(":root") for p in parts)


def check_module_css(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]:
    """Warn when module CSS sits in the file with the wrong cascade position."""
    diagnostics: list[Diagnostic] = []

    styles = src_dir / STYLES_CSS
    if styles.is_file():
        for prelude, line in _top_level_preludes(styles.read_text("utf-8")):
            at_rule = prelude.split()[0].lower() if prelude.split() else ""
            if at_rule in THEME_ONLY_AT_RULES:
                diagnostics.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM022",
                        message=(
                            f"{at_rule} in {STYLES_CSS} is inert — that file is "
                            "imported into layer(components)"
                        ),
                        module_name=mod.meta.name,
                        file=f"{styles}:{line}",
                        suggestion=(
                            f"Move the {at_rule} block to {src_dir / THEME_CSS}, which is "
                            "imported unlayered so its tokens actually register"
                        ),
                    )
                )

    theme = src_dir / THEME_CSS
    if theme.is_file():
        for prelude, line in _top_level_preludes(theme.read_text("utf-8")):
            if prelude.startswith("@") or _is_root_selector(prelude):
                continue
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM023",
                    message=(
                        f"Unlayered rule '{prelude}' in {THEME_CSS} outranks every Tailwind utility"
                    ),
                    module_name=mod.meta.name,
                    file=f"{theme}:{line}",
                    suggestion=(
                        f"Move it to {src_dir / STYLES_CSS}, which is imported into "
                        "layer(components) so utilities still win"
                    ),
                )
            )

    return diagnostics
