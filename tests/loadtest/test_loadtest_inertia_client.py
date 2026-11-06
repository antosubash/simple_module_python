"""The load scenario must exercise successful, catalog-cached Inertia visits."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from requests import Response
from requests.adapters import BaseAdapter


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.setenv("LOCUST_SKIP_MONKEY_PATCH", "1")
    spec = importlib.util.spec_from_file_location(
        "load_scenario", Path(__file__).with_name("locustfile.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_COOKIE", "test-cookie")
    return module


def user_for(scenario, text, status=200):
    from locust.env import Environment
    from locust.event import Events

    state = SimpleNamespace(text=text, status=status, calls=[], results=[])

    class OfflineAdapter(BaseAdapter):
        def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
            state.calls.append(request)
            response = Response()
            response.status_code = state.status
            response._content = state.text.encode()
            response.url = request.url
            response.request = request
            return response

        def close(self):
            pass

    environment = Environment(events=Events())
    environment.events.request.add_listener(lambda **result: state.results.append(result))
    scenario.AuthedUser.host = "http://loadtest.invalid"
    user = scenario.AuthedUser(environment)
    user.client.mount("http://", OfflineAdapter())
    return user, state


def page_html(version="asset-123", locale="de", audience="full"):
    page = {
        "version": version,
        "props": {"i18n": {"locale": locale, "audience": audience, "messages": {"hello": "Hallo"}}},
    }
    return (
        f'<script data-page="app" type="application/json">{json.dumps(page)}</script>'
        '<div id="app"></div>'
    )


def test_loadtest_bootstraps_and_sends_browser_headers(scenario):
    user, state = user_for(scenario, page_html())
    user.on_start()
    assert state.calls[0].path_url == "/dashboard/"
    assert state.calls[0].headers["Accept"] == "text/html"
    assert state.calls[0].headers["Cookie"] == "session=test-cookie"
    assert "X-Inertia" not in state.calls[0].headers
    for task in (user.dashboard_view, user.users_list_view):
        task()
        assert {k: v for k, v in state.calls[-1].headers.items() if k.startswith("X-")} == {
            "X-Inertia": "true",
            "X-Inertia-Version": "asset-123",
            "X-SM-I18n": "de:full",
        }
        assert state.results[-1]["exception"] is None
    user.dashboard_stats()
    assert "X-Inertia-Version" not in state.calls[-1].headers
    assert "X-SM-I18n" not in state.calls[-1].headers


@pytest.mark.parametrize(
    "text,status",
    [
        ("login page", 200),
        (page_html(), 409),
        (page_html(version=None), 200),
        (page_html(audience="public"), 200),
        (page_html(locale=None), 200),
        ('<script data-page="app">{"version":"v1","props":{"i18n":null}}</script>', 200),
    ],
)
def test_loadtest_stops_on_invalid_bootstrap(scenario, text, status):
    from locust.exception import StopUser

    user, state = user_for(scenario, text, status)
    with pytest.raises(StopUser):
        user.on_start()
    assert state.results[-1]["exception"] is not None


def test_loadtest_does_not_accept_version_conflicts(scenario):
    user, state = user_for(scenario, page_html())
    user.on_start()
    state.status = 409
    user.dashboard_view()
    assert state.results[-1]["exception"] is not None
