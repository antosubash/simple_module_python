"""The image smoke gate must catch missing assets and clean up failed boots."""

import io
import signal
import subprocess
from urllib.error import HTTPError, URLError

import pytest

from scripts import ci_docker_smoke as smoke


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<script src="/static/dist/assets/app-123.js"></script>',
            "/static/dist/assets/app-123.js",
        ),
        ("<link href='/static/dist/app.css?v=1&amp;x=2'>", "/static/dist/app.css?v=1&x=2"),
        ('<script src="http://localhost:5050/app.js"></script>', None),
    ],
)
def test_extract_built_asset(html, expected):
    if expected is None:
        with pytest.raises(RuntimeError, match="/static/dist"):
            smoke.first_asset(html)
    else:
        assert smoke.first_asset(html) == expected


@pytest.mark.parametrize(
    "failure", [None, "warming", "asset", "missing", "health", "run", "signal"]
)
def test_smoke_checks_http_and_always_removes_container(monkeypatch, capsys, failure):
    commands = []
    requests = []
    failed = failure not in (None, "warming")

    def docker(args, **kwargs):
        commands.append(args)
        if args[1] == "run" and failure == "run":
            raise subprocess.CalledProcessError(1, args)
        stdout = "127.0.0.1:49153\n" if args[1] == "port" else "container-id\n"
        return subprocess.CompletedProcess(args, 0, stdout)

    def urlopen(url, *, timeout):
        requests.append(url)
        assert timeout > 0
        if url.endswith("/health") and failure == "signal":
            smoke.terminate(signal.SIGTERM, None)
        if url.endswith("/health") and failure == "health":
            raise URLError("not ready")
        if failure == "warming" and len(requests) == 1:
            raise URLError("starting")
        if url.endswith("app.js") and failure == "asset":
            raise HTTPError(url, 404, "Not Found", {}, None)
        body = (
            b"<html>No bundle</html>"
            if failure == "missing"
            else (b'<script src="/static/dist/assets/app.js"></script>')
        )
        response = io.BytesIO(body)
        response.status = 200
        return response

    monkeypatch.setattr(smoke.subprocess, "run", docker)
    monkeypatch.setattr(smoke, "urlopen", urlopen)
    ticks = iter([0, 0, 121])
    monkeypatch.setattr(smoke.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(smoke.time, "sleep", lambda _: None)

    if failure == "signal":
        with pytest.raises(SystemExit):
            smoke.main()
    else:
        assert smoke.main() == (1 if failed else 0)

    assert commands[-1][1:3] == ["rm", "-f"]
    assert any(command[1] == "logs" for command in commands) == failed
    if not failed:
        expected = [
            "http://127.0.0.1:49153/health",
            "http://127.0.0.1:49153/",
            "http://127.0.0.1:49153/static/dist/assets/app.js",
        ]
        if failure == "warming":
            expected.insert(0, "http://127.0.0.1:49153/health")
        assert requests == expected
        assert "passed" in capsys.readouterr().out


def test_http_requires_exactly_200(monkeypatch):
    response = io.BytesIO(b"unexpected")
    response.status = 201
    monkeypatch.setattr(smoke, "urlopen", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="201"):
        smoke.get("http://127.0.0.1/")
