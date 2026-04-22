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

The corresponding pytest fixtures are ``fake_event_bus``, ``test_app``,
``test_client``, and ``test_db_session``. See ``simple_module_test.plugin``
for their definitions.
"""

from simple_module_test.app_factory import build_test_app
from simple_module_test.fake_events import FakeEventBus, RecordedEvent
from simple_module_test.session_cookie import forge_session_cookie

__all__ = [
    "FakeEventBus",
    "RecordedEvent",
    "build_test_app",
    "forge_session_cookie",
]
