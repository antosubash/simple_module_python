"""OAuth factory failures are logged without their message (#964)."""

import logging
from types import SimpleNamespace

from fastapi import FastAPI
from users.core.settings import UsersSettings


def test_factory_errors_never_log_their_message(caplog):
    from users.contracts import register_oauth_provider
    from users.core.startup import _build_oauth_clients

    def _leaky(app):
        raise RuntimeError("client_secret=super-secret-value rejected")

    app = FastAPI()
    app.state.users = SimpleNamespace(settings=UsersSettings())
    register_oauth_provider(app, "leaky", _leaky)
    _build_oauth_clients(app)
    text = "\n".join(
        logging.Formatter("%(message)s").format(r) + (r.exc_text or "") for r in caplog.records
    )
    assert "leaky" in text and "RuntimeError" in text
    assert "super-secret-value" not in text
    assert all(r.exc_info is None for r in caplog.records)
