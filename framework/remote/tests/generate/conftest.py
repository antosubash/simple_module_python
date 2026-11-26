import io

import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.http.client import ApiClient


class _Harness:
    """A RunContext over a mock transport; ``run`` returns the exit code."""

    def __init__(self, handler, root=None):
        self.requests: list[httpx.Request] = []
        self.out, self.err = io.StringIO(), io.StringIO()
        env = Environment("prod", "https://app.example")

        def wrapped(req):
            self.requests.append(req)
            return handler(req)

        self.ctx = RunContext(
            env=env,
            client_factory=lambda: ApiClient(
                env, "tok", user_agent="t/1", transport=httpx.MockTransport(wrapped)
            ),
            is_tty=False,
            stdout=self.out,
            stderr=self.err,
            stdin=io.StringIO(""),
            prompt=lambda t: "",
            root=root or {"paths": {}},
        )

    def run(self, op, **values) -> int:
        return run_operation(self.ctx, op, values)


@pytest.fixture
def execute_harness():
    return _Harness
