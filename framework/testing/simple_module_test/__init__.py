"""Shared pytest fixtures and helpers for SimpleModule module authors.

Install with ``pip install simple_module_test[dev]`` (or add it to
``[project.optional-dependencies].dev`` of your module). The pytest plugin
registers its fixtures automatically via the ``pytest11`` entry_point — no
imports needed in your test files.

Primary exports:

* :class:`FakeEventBus` — records every ``publish``/``publish_nowait`` call
  so tests can assert on emitted events without wiring real subscribers.
* :func:`build_test_app` — return a minimal FastAPI app loading exactly
  one module, with an in-memory SQLite DB.

The pytest plugin auto-registers these fixtures (no imports needed):
``fake_event_bus``, ``build_test_app``, ``settings``, ``db_state``,
``engine``, ``db_session``, ``app``, ``client``, and ``authenticated_client``.
See ``simple_module_test.plugin`` (and ``simple_module_test.fixtures``) for
their definitions. ``authenticated_client`` additionally requires the ``users``
module to be installed — it seeds an admin via ``users.bootstrap``.
"""

from simple_module_test.app_factory import build_test_app
from simple_module_test.fake_events import FakeEventBus, RecordedEvent
from simple_module_test.routes import effective_route_paths
from simple_module_test.session_cookie import forge_session_cookie

__all__ = [
    "FakeEventBus",
    "RecordedEvent",
    "build_test_app",
    "effective_route_paths",
    "forge_session_cookie",
]
