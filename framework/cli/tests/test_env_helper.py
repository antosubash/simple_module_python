"""``set_env_key`` is the single helper that edits scaffold-time .env files.

A regression here writes a duplicate ``KEY=`` line or, worse, leaves the old
value unstripped — both manifest as "my recipe didn't take effect" which is
hard to debug downstream.
"""

from __future__ import annotations

from simple_module_cli._env import set_env_key


def test_appends_to_empty_body():
    assert set_env_key("", "FOO", "bar") == "FOO=bar\n"


def test_replaces_existing_key():
    body = "FOO=old\nBAR=keep\n"
    out = set_env_key(body, "FOO", "new")
    # Replaced line lives at the bottom (append-after-strip strategy).
    assert "FOO=old" not in out
    assert "FOO=new\n" in out
    assert "BAR=keep" in out


def test_unrelated_lines_preserved_in_order():
    body = "A=1\nB=2\nC=3\n"
    out = set_env_key(body, "Z", "9")
    lines = out.splitlines()
    assert lines[0] == "A=1"
    assert lines[1] == "B=2"
    assert lines[2] == "C=3"
    assert lines[-1] == "Z=9"


def test_idempotent_when_key_already_at_value():
    body = "FOO=bar\n"
    once = set_env_key(body, "FOO", "bar")
    twice = set_env_key(once, "FOO", "bar")
    assert once == twice == "FOO=bar\n"


def test_prefix_match_is_exact():
    """``KEY=`` must not match ``KEY_LONGER=``."""
    body = "FOO_BAR=keep_me\n"
    out = set_env_key(body, "FOO", "new")
    assert "FOO_BAR=keep_me" in out
    assert "FOO=new" in out


def test_output_always_ends_with_newline():
    body = "X=1"  # no trailing newline
    out = set_env_key(body, "Y", "2")
    assert out.endswith("\n")
