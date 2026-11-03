"""Inertia assertions work for document loads and subsequent protocol visits."""

import httpx
import pytest
import simple_module_test
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from jinja2.utils import htmlsafe_json_dumps
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia import (
    InertiaConfig,
    defer,
    inertia_dependency_factory,
    merge,
    optional,
)


def page_response(**fields):
    return httpx.Response(
        200,
        headers={"X-Inertia": "true"},
        json={
            "component": "Probe",
            "props": {"auth": {"user": {"email": "a@test"}}, "items": [{"id": 1}], "nil": None},
            "url": "/probe?q=1",
            "version": "build",
            **fields,
        },
    )


def test_json_page_assertions_chain():
    page = simple_module_test.inertia_page(page_response(deferredProps={"slow": ["stats"]}))
    assert (
        page.assert_component("Probe")
        .assert_url("/probe?q=1")
        .assert_version("build")
        .has("items", count=1)
        .has("auth.user", count=1)
        .has("nil")
        .where("nil", None)
        .where("auth.user.email", "a@test")
        .where("items.0.id", lambda value: value > 0)
        .missing("items.1")
        .missing("items.-1")
        .missing("nil.child")
        .deferred("slow", "stats")
        is page
    )
    assert page.component == "Probe"
    assert page.props["items"] == [{"id": 1}]
    assert page.url == "/probe?q=1"
    assert page.version == "build"


@pytest.mark.parametrize("html", [False, True])
def test_parsing_preserves_html_safe_json_and_metadata(html):
    fields = {
        "props": {"text": "<script>&lt; ' snowman ☃"},
        "deferredProps": {"default": ["slow"]},
        "mergeProps": ["items"],
        "onceProps": {"key": {"prop": "lookup"}},
        "scrollProps": {"items": {"currentPage": 1}},
        "sharedProps": ["auth"],
        "rescuedProps": ["slow"],
        "encryptHistory": True,
        "clearHistory": True,
    }
    response = page_response(**fields)
    if html:
        blob = htmlsafe_json_dumps(response.json())
        response = httpx.Response(
            200,
            text=f'<html><script>ignored</script><script type="application/json" '
            f"data-page='app'>\n{blob}\n</script></html>",
        )
    page = simple_module_test.InertiaPage.from_response(response)
    assert page.props == fields["props"]
    assert page.deferred_props == fields["deferredProps"]
    assert page.merge_props == fields["mergeProps"]
    assert page.once_props == fields["onceProps"]
    assert page.scroll_props == fields["scrollProps"]
    assert page.shared_props == fields["sharedProps"]
    assert page.rescued_props == fields["rescuedProps"]
    assert page.encrypt_history is True
    assert page.clear_history is True


def test_optional_page_fields_default_to_empty_or_false():
    page = simple_module_test.inertia_page(page_response())
    assert page.deferred_props == page.once_props == page.scroll_props == {}
    assert page.merge_props == page.shared_props == page.rescued_props == []
    assert page.encrypt_history is page.clear_history is False


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="plain response"),
        httpx.Response(200, json={"detail": "API response"}),
        httpx.Response(200, headers={"X-Inertia": "true"}, text="bad JSON"),
        page_response(component=None),
        page_response(props=[]),
        httpx.Response(200, headers={"X-Inertia": "true"}, json=[]),
        httpx.Response(200, text='<script data-page="app" type="application/json">{</script>'),
        httpx.Response(200, text='<script data-page="app" type="text/plain">{}</script>'),
        httpx.Response(200, text='<script data-page="app" type="application/json">{}'),
    ],
)
def test_invalid_responses_raise_clear_assertions(response):
    with pytest.raises(AssertionError, match="Not a valid Inertia response"):
        simple_module_test.inertia_page(response)


@pytest.mark.parametrize(
    ("method", "args", "message"),
    [
        ("assert_component", ("Other",), "component.*Other.*Probe"),
        ("assert_url", ("/other",), "url.*/other.*/probe"),
        ("assert_version", ("stale",), "version.*stale.*build"),
        ("has", ("auth.missing",), "auth.missing.*Available.*user"),
        ("has", ("items.2",), "items.2.*Available.*0"),
        ("has", ("items.bad",), "items.bad.*Available.*0"),
        ("has", ("nil.child",), "nil.child.*Available"),
        ("has", ("items", 2), "items.*2.*1"),
        ("has", ("nil", 1), "nil.*count"),
        ("missing", ("nil",), "nil.*present.*Available"),
        ("where", ("items.0.id", 2), "items.0.id.*2.*1"),
        ("where", ("items.0.id", lambda value: value < 0), "items.0.id.*predicate.*1"),
        ("where", ("absent", None), "absent.*Available.*items"),
        ("deferred", ("unknown",), "unknown.*Available.*slow"),
        ("deferred", ("slow", "other"), "other.*Available.*stats"),
    ],
)
def test_assertion_failures_are_actionable(method, args, message):
    page = simple_module_test.inertia_page(page_response(deferredProps={"slow": ["stats"]}))
    with pytest.raises(AssertionError, match=message):
        getattr(page, method)(*args)


@pytest.fixture
async def helper_client(build_test_app, tmp_path):
    class ProbeModule(ModuleBase):
        meta = ModuleMeta(name="Probe")

    app = build_test_app(ProbeModule)
    (tmp_path / "index.html").write_text("{% inertia_body %}", encoding="utf-8")
    config = InertiaConfig(templates=Jinja2Templates(directory=tmp_path), version="build")
    app.state.inertia_dependency = inertia_dependency_factory(config)

    async def probe(inertia: InertiaDep):
        return await inertia.render(
            "Probe",
            {
                "name": "Ada",
                "extra": optional(lambda: "requested"),
                "stats": defer(lambda: {"total": 3}),
                "report": defer(lambda: "ready", group="reports"),
                "items": merge([{"id": 1}]),
            },
        )

    app.router.routes.insert(0, APIRoute("/inertia-helper-probe", probe, methods=["GET"]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Inertia-Version": "build"},
    ) as client:
        yield client


@pytest.fixture
async def probe_page(helper_client):
    response = await helper_client.get("/inertia-helper-probe?q=1")
    assert response.status_code == 200
    return simple_module_test.inertia_page(response)


async def test_real_document_and_json_visits(probe_page, helper_client):
    probe_page.assert_component("Probe").where("name", "Ada").missing("extra")
    probe_page.deferred("default", "stats").deferred("reports", "report")
    assert probe_page.merge_props == ["items"]
    response = await helper_client.get(probe_page.url, headers={"X-Inertia": "true"})
    page = simple_module_test.inertia_page(response)
    assert page.props == probe_page.props
    assert page.deferred_props == probe_page.deferred_props


async def test_reload_only_and_except(probe_page, helper_client):
    page = await probe_page.reload_only(helper_client, "extra", "items")
    page.where("extra", "requested").has("items", 1).missing("name")
    assert page is not probe_page
    assert page.url == probe_page.url
    page = await probe_page.reload_except(helper_client, "items")
    page.where("name", "Ada").missing("items").where("extra", "requested")


async def test_load_deferred_group_and_all(probe_page, helper_client):
    page = await probe_page.load_deferred(helper_client, "reports")
    page.where("report", "ready").missing("stats").missing("name")
    page = await probe_page.load_deferred(helper_client)
    page.where("stats.total", 3).where("report", "ready").missing("name")
    with pytest.raises(AssertionError, match=r"unknown.*Available.*reports"):
        await probe_page.load_deferred(helper_client, "unknown")


async def test_followup_headers_use_page_version():
    async def respond(request):
        assert request.url.path == "/probe"
        assert request.url.query == b"q=1"
        assert request.headers["X-Inertia"] == "true"
        assert request.headers["X-Inertia-Version"] == "build"
        assert request.headers["X-Inertia-Partial-Component"] == "Probe"
        assert request.headers["X-Inertia-Partial-Data"] == "auth.user,items"
        assert "X-Inertia-Partial-Except" not in request.headers
        return page_response()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://test"
    ) as client:
        await simple_module_test.inertia_page(page_response()).reload_only(
            client, "auth.user", "items"
        )


async def test_no_deferred_props_does_not_reload():
    async def unexpected(request):
        pytest.fail("A page without deferred props must not issue a full reload")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        page = simple_module_test.inertia_page(page_response())
        loaded = await page.load_deferred(client)
        assert loaded.props == page.props
