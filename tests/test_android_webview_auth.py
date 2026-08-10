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
