"""The release preflight retries a flaky PyPI before failing the release."""

import ssl
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from scripts import release_preflight


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://pypi.org", code, "x", {}, None)


@pytest.fixture
def pypi(monkeypatch):
    """Answer each probe from a list of outcomes; record how many were made."""
    outcomes: list[object] = []
    calls: list[str] = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        outcome = outcomes.pop(0) if outcomes else BytesIO(b"{}")
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(release_preflight, "urlopen", fake_urlopen)
    monkeypatch.setattr(release_preflight, "sleep", lambda _: None)
    monkeypatch.setattr(release_preflight, "parse_publish_matrix", lambda _: ["simple_module_a"])
    return outcomes, calls


def test_a_transient_handshake_timeout_is_retried(pypi) -> None:
    outcomes, calls = pypi
    outcomes += [URLError(ssl.SSLError("The handshake operation timed out")), _http_error(503)]
    assert release_preflight.main([]) == 0
    assert len(calls) == 3


def test_a_persistent_network_failure_still_fails(pypi, capsys) -> None:
    outcomes, calls = pypi
    outcomes += [URLError("down")] * release_preflight.ATTEMPTS
    assert release_preflight.main([]) == 1
    assert len(calls) == release_preflight.ATTEMPTS
    assert "cannot check PyPI" in capsys.readouterr().out


def test_a_404_is_not_retried(pypi, capsys) -> None:
    outcomes, calls = pypi
    outcomes.append(_http_error(404))
    assert release_preflight.main([]) == 1
    assert len(calls) == 1
    assert "pending publisher" in capsys.readouterr().out
