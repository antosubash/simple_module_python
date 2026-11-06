"""Installed host version discovery is constant within a process."""

from simple_module_hosting._api_version import default_api_version


def test_host_version_discovery_is_cached(monkeypatch):
    monkeypatch.setattr("importlib.metadata.version", lambda name: "4.5.6")
    assert default_api_version() == "4.5.6"
    monkeypatch.setattr("importlib.metadata.version", lambda name: "9.9.9")
    assert default_api_version() == "4.5.6"
