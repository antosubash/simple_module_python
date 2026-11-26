import click
import httpx
import pytest

TOKEN = "tok"  # the execute_harness token
SPLIT = "‮".join(TOKEN)  # t<bidi>o<bidi>k: sanitising reassembles the token


def test_tenant_hint_sanitises_before_redacting(execute_harness, make_op, make_tty):
    h = execute_harness(lambda r: httpx.Response(403, json={"detail": f"tenant {SPLIT}"}))
    h.ctx.stderr = h.err = make_tty()
    assert h.run(make_op()) == 4
    hint = next(ln for ln in h.err.getvalue().splitlines() if ln.startswith("hint:"))
    shown = hint.split("tenant: ", 1)[1].split("; pass")[0]  # the server text only
    assert TOKEN not in shown and "\u202e" not in hint


def test_format_refusal_does_not_echo_the_content_type(execute_harness, make_op):
    h = execute_harness(
        lambda r: httpx.Response(200, text="x", headers={"Content-Type": f"text/{TOKEN}"})
    )
    with pytest.raises(click.ClickException) as info:
        h.run(make_op(), output="json")
    assert TOKEN not in info.value.message


def test_unknown_column_error_is_sanitised_and_redacted(execute_harness, make_op, make_tty):
    h = execute_harness(lambda r: httpx.Response(200, json=[{SPLIT: 1}]))
    h.ctx.stderr = h.err = make_tty()
    with pytest.raises(click.ClickException) as info:
        h.run(make_op(), output="table", columns="nope")
    assert TOKEN not in info.value.message and "‮" not in info.value.message
