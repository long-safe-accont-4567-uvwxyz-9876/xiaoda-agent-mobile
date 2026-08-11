import time

import pytest
from fastapi import HTTPException

from web.routers import auth


class RequestStub:
    def __init__(self, authorization: str = "", cookie: str = ""):
        self.headers = {"Authorization": authorization} if authorization else {}
        self.cookies = {"xiaoda_session": cookie} if cookie else {}
        self.state = type("State", (), {})()


@pytest.mark.asyncio
async def test_short_webview_session_authenticates_without_bearer_in_web_storage():
    token, _ = auth._issue_token()
    session = auth._issue_webview_session(token)

    assert session.handle != token
    assert await auth.get_current_user(RequestStub(cookie=session.handle)) == "webui"
    assert await auth.get_current_user(RequestStub(authorization=f"Bearer {session.handle}")) == "webui"


@pytest.mark.asyncio
async def test_expired_webview_session_is_rejected(monkeypatch):
    token, _ = auth._issue_token()
    session = auth._issue_webview_session(token)
    monkeypatch.setattr(time, "time", lambda: session.expires_at + 1)

    with pytest.raises(HTTPException) as error:
        await auth.get_current_user(RequestStub(cookie=session.handle))

    assert error.value.status_code == 401


def test_websocket_auth_accepts_short_cookie_and_rejects_query_tokens():
    token, _ = auth._issue_token()
    session = auth._issue_webview_session(token)

    assert auth.resolve_webview_session(session.handle) == token
    assert auth.resolve_webview_session(token) is None


@pytest.mark.asyncio
async def test_short_session_slides_and_tracks_rotated_bearer(monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    token, _ = auth._issue_token()
    session = auth._issue_webview_session(token, lifetime_seconds=300)
    request = RequestStub(cookie=session.handle)

    now += 250
    assert await auth.get_current_user(request) == "webui"
    assert request.state.webview_session_handle == session.handle
    assert request.state.webview_session_expiry == now + 300

    now += 100
    assert auth.resolve_webview_session(session.handle) == token


@pytest.mark.asyncio
async def test_short_session_survives_bearer_sliding_renewal(monkeypatch):
    now = 2_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    monkeypatch.setattr(auth, "_issue_token", lambda: ("new-token", now + 7 * 86400))
    monkeypatch.setattr(auth, "_validate_token", lambda token: token in {"old-token", "new-token"})
    monkeypatch.setattr(auth, "_extract_expiry", lambda token: now + 60 if token == "old-token" else now + 7 * 86400)
    monkeypatch.setattr(auth, "_revoke_token", lambda token: None)
    session = auth._issue_webview_session("old-token", lifetime_seconds=300)
    request = RequestStub(cookie=session.handle)

    assert await auth.get_current_user(request) == "webui"
    assert auth.resolve_webview_session(session.handle) == "new-token"
    assert not hasattr(request.state, "new_token")


def test_webview_cookie_protocol_is_single_source():
    assert auth.WEBVIEW_SESSION_COOKIE_NAME == "xiaoda_session"
    assert auth.WEBVIEW_SESSION_COOKIE_MAX_AGE == 300
    assert auth.WEBVIEW_SESSION_COOKIE_SAMESITE == "none"


def test_explicit_short_session_renewal_keeps_handle_and_extends_expiry(monkeypatch):
    now = 3_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    token, _ = auth._issue_token()
    session = auth._issue_webview_session(token)

    now += 250
    renewed = auth.renew_webview_session(session.handle)

    assert renewed is not None
    assert renewed.handle == session.handle
    assert renewed.expires_at == now + auth.WEBVIEW_SESSION_COOKIE_MAX_AGE
    assert auth.resolve_webview_session(session.handle) == token
