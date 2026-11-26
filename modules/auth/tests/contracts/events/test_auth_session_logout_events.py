"""Session logout events preserve the dated Request calling convention (#1129)."""

import warnings
from uuid import UUID

import pytest
from auth.contracts.events import session_logout_event
from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_BEARER
from starlette.requests import Request


@pytest.mark.parametrize("keyword", [False, True], ids=["positional", "request-keyword"])
@pytest.mark.parametrize("local_account", [False, True], ids=["external", "local"])
def test_legacy_request_returns_session_identity_and_warns(keyword, local_account):
    request = Request({"type": "http"})
    request.state.user = UserContext(
        id="74fefc26-66cb-4914-a51f-c88f27e66bb3", email="session@example.com", name="Session"
    )

    with pytest.warns(DeprecationWarning, match=r"session_logout_event.*0\.0\.52"):
        if keyword:
            event = session_logout_event(request=request, local_account=local_account)
        else:
            event = session_logout_event(request, local_account=local_account)

    assert event is not None
    assert event.user_id == (
        UUID("74fefc26-66cb-4914-a51f-c88f27e66bb3")
        if local_account
        else "74fefc26-66cb-4914-a51f-c88f27e66bb3"
    )
    assert event.email == "session@example.com"


@pytest.mark.parametrize("has_bearer", [False, True], ids=["missing-user", "bearer-user"])
def test_legacy_request_without_session_identity_returns_none_and_warns(has_bearer):
    request = Request({"type": "http"})
    if has_bearer:
        request.state.user = UserContext(
            id="bearer", email="bearer@example.com", name="Bearer", auth_kind=AUTH_KIND_BEARER
        )

    with pytest.warns(DeprecationWarning, match=r"session_logout_event.*0\.0\.52"):
        assert session_logout_event(request, local_account=False) is None


def test_validated_session_user_returns_event_without_warning():
    user = UserContext(id="ExternalSubject", email="session@example.com", name="Session")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        event = session_logout_event(user=user, local_account=False)

    assert event is not None
    assert event.user_id == "ExternalSubject"
    assert event.email == "session@example.com"
    assert not caught


def test_none_returns_none_without_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert session_logout_event(None, local_account=True) is None

    assert not caught


def test_user_and_request_cannot_be_combined():
    user = UserContext(id="session", email="session@example.com", name="Session")
    request = Request({"type": "http"})

    with pytest.raises(TypeError, match="either user or request"):
        session_logout_event(user, request=request, local_account=False)
