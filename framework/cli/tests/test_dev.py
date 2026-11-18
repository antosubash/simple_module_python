"""Dev owns only its two child process groups and shares one resolved environment."""

import signal
import subprocess
from types import SimpleNamespace

import pytest


def test_port_selection_skips_busy_ports_and_rejects_explicit_port(monkeypatch):
    from simple_module_cli import dev_cmd

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            if address[1] in {5050, 5051}:
                raise OSError("in use")

    monkeypatch.setattr(dev_cmd.socket, "socket", lambda *a: Socket())
    assert dev_cmd.choose_vite_port(None, api_port=8000) == 5052
    assert dev_cmd.choose_vite_port(None, api_port=5052) == 5053
    with pytest.raises(ValueError, match="5051"):
        dev_cmd.choose_vite_port(5051, api_port=8000)
    with pytest.raises(ValueError, match="API"):
        dev_cmd.choose_vite_port(8000, api_port=8000)


@pytest.fixture
def dev_project(tmp_path, monkeypatch):
    from simple_module_cli import dev_cmd

    host = tmp_path / "host"
    (host / "client_app").mkdir(parents=True)
    (host / "main.py").write_text("app = None")
    # A temporary fixture, never the invoking project's dotenv file.
    (tmp_path / ".env").write_text('DEMO="file"\nSM_VITE_DEV_URL=http://localhost:9999\n')
    monkeypatch.setenv("DEMO", "exported")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(dev_cmd, "choose_vite_port", lambda *a, **kw: 5207)
    monkeypatch.setattr(dev_cmd, "check_port", lambda _: None)
    monkeypatch.setattr(dev_cmd.shutil, "which", lambda name: f"/bin/{name}")
    calls, children, killed = [], [], []
    monkeypatch.setattr(dev_cmd, "run_generation", lambda root: calls.append("gen"))
    monkeypatch.setattr(dev_cmd.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    return SimpleNamespace(root=tmp_path, calls=calls, children=children, killed=killed)


@pytest.mark.parametrize("stop", ["exit", "vite_exit", "sigint", "sigterm", "spawn_failure"])
def test_dev_generates_first_shares_env_and_cleans_up(dev_project, monkeypatch, stop):
    from simple_module_cli import dev_cmd

    p = dev_project
    handlers = {}
    monkeypatch.setattr(dev_cmd.signal, "getsignal", lambda sig: signal.SIG_DFL)
    monkeypatch.setattr(dev_cmd.signal, "signal", lambda sig, fn: handlers.update({sig: fn}))

    class Child:
        def __init__(self, pid):
            self.pid = pid

        def poll(self):
            if stop == "vite_exit" and self.pid == 4100:
                return None
            if stop == "sigint":
                handlers[signal.SIGINT](signal.SIGINT, None)
            if stop == "sigterm":
                handlers[signal.SIGTERM](signal.SIGTERM, None)
            return 7

        def wait(self, timeout):
            return 7

    def popen(cmd, **kw):
        assert p.calls[0] == "gen"
        p.calls.append((cmd, kw))
        if stop == "spawn_failure" and p.children:
            raise OSError("npm failed to launch")
        child = Child(4100 + len(p.children))
        p.children.append(child)
        return child

    monkeypatch.setattr(dev_cmd.subprocess, "Popen", popen)
    if stop == "spawn_failure":
        with pytest.raises(OSError, match="npm"):
            dev_cmd.run_dev(p.root, port=8201)
    else:
        expected = {"exit": 7, "vite_exit": 7, "sigint": 130, "sigterm": 143}[stop]
        assert dev_cmd.run_dev(p.root, port=8201) == expected
    for _cmd, kw in p.calls[1:]:
        assert kw["start_new_session"] is True
        assert kw["env"]["SM_VITE_DEV_URL"] == "http://localhost:5207"
        assert kw["env"]["DEMO"] == "exported"
        assert kw["cwd"] in (p.root, p.root / "host/client_app")
    api = p.calls[1][0]
    assert "8201" in api
    assert "host.main:app" in api
    assert "--reload-include" in api
    assert {pid for pid, sig in p.killed if sig == signal.SIGTERM} == {
        child.pid for child in p.children
    }
    assert handlers[signal.SIGINT] == signal.SIG_DFL
    assert handlers[signal.SIGTERM] == signal.SIG_DFL


def test_generation_failure_never_starts_children(dev_project, monkeypatch):
    from simple_module_cli import dev_cmd

    def failed_generation(_root):
        raise RuntimeError("generation failed")

    def unexpected_spawn(*args, **kwargs):
        pytest.fail("started a child after generation failed")

    monkeypatch.setattr(dev_cmd, "run_generation", failed_generation)
    monkeypatch.setattr(dev_cmd.subprocess, "Popen", unexpected_spawn)
    with pytest.raises(RuntimeError, match="generation failed"):
        dev_cmd.run_dev(dev_project.root)


def test_cleanup_kills_descendants_even_when_leader_exited(monkeypatch):
    from simple_module_cli.dev_cmd import stop_children

    killed = []
    monkeypatch.setattr("os.killpg", lambda pid, sig: killed.append((pid, sig)))
    child = SimpleNamespace(pid=7123, wait=lambda timeout: 0)
    stop_children([child])
    assert (7123, signal.SIGTERM) in killed
    assert (7123, signal.SIGKILL) in killed


def test_cleanup_escalates_and_reaps_stubborn_child(monkeypatch):
    from simple_module_cli.dev_cmd import stop_children

    waits, killed = [], []

    def wait(timeout):
        waits.append(timeout)
        if len(waits) == 1:
            raise subprocess.TimeoutExpired("child", timeout)
        return -9

    monkeypatch.setattr("os.killpg", lambda pid, sig: killed.append((pid, sig)))
    stop_children([SimpleNamespace(pid=7123, wait=wait)])
    assert killed[-1] == (7123, signal.SIGKILL)
    assert len(waits) == 2
