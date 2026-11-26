import click
import httpx
import pytest
from simple_module_remote.generate.operations import Param


def json_ok(data):
    return lambda req: httpx.Response(200, json=data)


def test_all_with_page_is_refused(execute_harness, make_op):
    op = make_op(
        params=tuple(
            Param(n, "query", False, {"type": "integer"}, "") for n in ("page", "per_page")
        )
    )
    root = {
        "paths": {
            "/api/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"type": "array", "items": {}}}
                            }
                        }
                    }
                }
            }
        }
    }
    h = execute_harness(json_ok([]), root)
    with pytest.raises(click.UsageError, match="page 1"):
        h.run(op, all_pages=True, q_page=2)
    assert h.requests == []


def test_multipart_missing_required_field_is_reported_before_sending(
    execute_harness, make_op, tmp_path
):
    op = make_op(
        method="POST",
        body_kind="multipart",
        body_schema={"type": "object", "required": ["file"], "properties": {"file": {}}},
    )
    h = execute_harness(json_ok({}))
    with pytest.raises(click.UsageError, match="missing required form fields: file"):
        h.run(op)
    assert h.requests == []
    f = tmp_path / "logo.png"
    f.write_bytes(b"abc")
    assert h.run(op, uploads=(f"file=@{f}",)) == 0
    dry = execute_harness(json_ok({}))
    dry.run(op, dry_run=True, uploads=(f"file={f}",))
    assert "filename logo.png, 3 bytes" in dry.out.getvalue()


def test_required_raw_body_without_body_file_is_refused_before_sending(execute_harness, make_op):
    op = make_op(method="PUT", body_kind="raw", body_required=True)
    h = execute_harness(lambda r: pytest.fail("sent"))
    with pytest.raises(click.UsageError, match="--body-file"):
        h.run(op)
    assert h.requests == []
