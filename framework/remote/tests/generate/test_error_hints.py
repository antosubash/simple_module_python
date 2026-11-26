"""Hints after an error answer fit the error (#1241)."""

import httpx
import pytest

LOGIN = "smdev --env prod login --token"
SCHEMA = "hint: this command comes from the bundled schema; run schema sync"


def _hints(h) -> list[str]:
    return [ln for ln in h.err.getvalue().splitlines() if ln.startswith("hint:")]


def _run(execute_harness, make_op, status, body):
    h = execute_harness(lambda r: httpx.Response(status, json=body))
    h.ctx.login_hint = LOGIN
    h.ctx.schema_hint = SCHEMA
    assert h.run(make_op(method="POST")) != 0
    # the request went out and its error was reported, so a missing hint means something
    assert len(h.requests) == 1 and f"error: HTTP {status}" in h.err.getvalue()
    return _hints(h)


@pytest.mark.parametrize(
    "detail",
    [
        "You cannot assign roles you do not hold.",
        "You cannot manage a more privileged account.",
        "The invitation has expired.",
        "Only authenticated administrators can do this.",
        {"code": "action_denied"},
    ],
)
def test_a_refused_action_does_not_suggest_logging_in_again(execute_harness, make_op, detail):
    assert _run(execute_harness, make_op, 403, {"detail": detail}) == []


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {"detail": "Unauthorized"}),
        (401, {}),
        (403, {}),
        (403, {"detail": "Not authenticated"}),
        (403, {"detail": "Token expired"}),
        (403, {"detail": "Authentication required"}),
        (403, {"detail": "Forbidden"}),
    ],
)
def test_a_credential_problem_still_suggests_logging_in(execute_harness, make_op, status, body):
    hints = _run(execute_harness, make_op, status, body)
    assert len(hints) == 1 and LOGIN in hints[0]


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, {"detail": "member_not_found"}),
        (404, {"detail": "Item 7 not found"}),
        (404, {"detail": "Not found"}),
        (422, {"detail": [{"type": [], "loc": ["body"], "msg": "x"}]}),
        (422, {"detail": [{"type": "bool_parsing", "loc": ["body", "enabled"], "msg": "x"}]}),
        (422, {"detail": "Choose a different slug."}),
    ],
)
def test_a_domain_error_does_not_blame_the_schema(execute_harness, make_op, status, body):
    assert _run(execute_harness, make_op, status, body) == []


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, {"detail": "Not Found"}),
        (404, {}),
        (405, {"detail": "Method Not Allowed"}),
        (422, {"detail": [{"type": "missing", "loc": ["body", "slug"], "msg": "x"}]}),
        (422, {"detail": [{"type": "extra_forbidden", "loc": ["body", "old"], "msg": "x"}]}),
    ],
)
def test_a_route_or_shape_mismatch_suggests_schema_sync(execute_harness, make_op, status, body):
    assert _run(execute_harness, make_op, status, body) == [SCHEMA]
