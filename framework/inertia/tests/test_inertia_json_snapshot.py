"""Pre-serialized catalogs keep wire bytes and partial filtering unchanged."""

import json
from datetime import UTC, datetime

import pytest
from jinja2.utils import htmlsafe_json_dumps
from simple_module_inertia._json_snapshot import (
    _HTML_ENCODER,
    _RESPONSE_ENCODER,
    JsonSnapshot,
    dumps,
)
from simple_module_inertia.page import _is_plain_json, build_page, encode_page
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props
from simple_module_inertia.response import json_response
from starlette.responses import JSONResponse


async def _page(messages, headers=None, rich=False):
    resolved = await resolve_props(
        {"when": datetime(2026, 11, 5, tzinfo=UTC)} if rich else {},
        {"i18n": {"messages": messages}},
        "C",
        InertiaRequest.from_headers(headers or {}, "GET"),
    )
    return build_page(component="C", resolved=resolved, url="/", version="v", errors={})


@pytest.mark.parametrize("rich", [False, True])
async def test_snapshot_skips_walks_and_preserves_json_bytes(rich, monkeypatch):
    messages = {"a": "é </script><!-- & ' \u2028", "b": '"\\ literal { }', "c": "plain"}
    snapshot = JsonSnapshot(messages)

    def no_walk(*args, **kwargs):
        pytest.fail("a pre-serialized catalog was walked")

    snapshot.items = no_walk
    for encoder in (_HTML_ENCODER, _RESPONSE_ENCODER):
        original = encoder.encode

        def no_reencode(value, encode=original):
            assert not isinstance(value, JsonSnapshot), "catalog was re-encoded"
            return encode(value)

        monkeypatch.setattr(encoder, "encode", no_reencode)
    plain = await _page(messages, rich=rich)
    cached = await _page(snapshot, rich=rich)
    assert cached["props"]["i18n"]["messages"] is snapshot
    if not rich:
        assert _is_plain_json(cached)
    assert json_response(cached).body == JSONResponse(encode_page(plain)).body
    expected = str(htmlsafe_json_dumps(encode_page(plain)))
    actual = str(htmlsafe_json_dumps(encode_page(cached), dumps=dumps))
    assert actual == expected
    assert "</script>" not in actual
    assert "\\u003c/script\\u003e" in actual


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ({"X-Inertia-Partial-Data": "i18n.messages.a"}, {"a": "A"}),
        ({"X-Inertia-Partial-Except": "i18n.messages.a"}, {"b": "B"}),
        ({"X-Inertia-Partial-Data": "i18n"}, {"a": "A", "b": "B"}),
    ],
)
async def test_snapshot_preserves_nested_partial_filters(selection, expected):
    page = await _page(
        JsonSnapshot({"a": "A", "b": "B"}),
        {
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "C",
            **selection,
        },
    )
    assert page["props"]["i18n"]["messages"] == expected


async def test_snapshot_keeps_encoder_sanitization():
    page = await _page(JsonSnapshot({"_sa_hidden": "secret", "visible": "ok"}))
    assert json_response(page).body == (
        b'{"component":"C","props":{"i18n":{"messages":{"visible":"ok"}},'
        b'"errors":{}},"url":"/","version":"v","sharedProps":["i18n"]}'
    )


@pytest.mark.parametrize("compact", [False, True])
def test_snapshot_serializer_matches_standard_json_for_surrounding_props(compact):
    data = {
        "catalog": {"key": "é"},
        "other": [None, True, False, 1, -1.25, [], {}],
        "keys": {1: "one", None: "null", False: "false", 2.5: "float"},
    }
    cached = {**data, "catalog": JsonSnapshot(data["catalog"])}
    options = (
        {"ensure_ascii": False, "allow_nan": False, "separators": (",", ":")} if compact else {}
    )
    assert dumps(cached, compact=compact) == json.dumps(data, **options)


def test_json_response_still_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="Out of range float"):
        json_response({"props": {"number": float("nan")}})


async def test_html_render_embeds_snapshot_with_standard_escaping(tmp_path):
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    from httpx import ASGITransport, AsyncClient
    from simple_module_inertia import Inertia, InertiaConfig
    from starlette.requests import Request

    (tmp_path / "index.html").write_text("{{ inertia.data | safe }}")
    config = InertiaConfig(
        templates=Jinja2Templates(directory=tmp_path),
        version="v",
        dev_url="http://localhost:5050",
        root_directory=".",
        use_flash_errors=False,
        use_flash_messages=False,
    )
    app = FastAPI()

    @app.get("/")
    async def render(request: Request):
        inertia = Inertia(request, config)
        messages = {"key": "é </script><!-- & '"}
        if request.headers.get("X-Test-Snapshot"):
            messages = JsonSnapshot(messages)
        inertia.share(i18n={"messages": messages})
        return await inertia.render("C")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        plain = await client.get("/")
        cached = await client.get("/", headers={"X-Test-Snapshot": "1"})
    assert cached.content == plain.content
    assert json.loads(cached.text)["props"]["i18n"]["messages"]["key"] == "é </script><!-- & '"
    assert "</script>" not in cached.text
