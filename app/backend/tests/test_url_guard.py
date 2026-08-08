from unittest.mock import MagicMock

import pytest

from app.backend.url_guard import UnsafeURLError, assert_public_http_url, safe_request


def test_rejects_loopback():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://127.0.0.1/admin")


def test_rejects_link_local_metadata():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_private_rfc1918():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://10.0.0.5/")


def test_rejects_ipv6_loopback():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://[::1]/")


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("ftp://8.8.8.8/file")


def test_rejects_url_without_hostname():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http:///no-host")


def test_accepts_public_ip_literal():
    # 8.8.8.8 is a numeric literal — getaddrinfo resolves it locally, no network needed.
    assert_public_http_url("http://8.8.8.8/") is None


def _fake_response(status_code, headers=None, redirect=False):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.is_redirect = redirect
    resp.is_permanent_redirect = False
    resp.close = MagicMock()
    return resp


def test_safe_request_follows_redirect_to_public_target():
    session = MagicMock()
    final = _fake_response(200)
    redirect = _fake_response(302, headers={"Location": "http://8.8.8.8/next"}, redirect=True)
    session.request.side_effect = [redirect, final]

    result = safe_request("GET", "http://8.8.8.8/start", session=session)

    assert result is final
    assert session.request.call_count == 2


def test_safe_request_blocks_redirect_to_private_target():
    session = MagicMock()
    redirect = _fake_response(302, headers={"Location": "http://127.0.0.1/internal"}, redirect=True)
    session.request.side_effect = [redirect]

    with pytest.raises(UnsafeURLError):
        safe_request("GET", "http://8.8.8.8/start", session=session)


def test_safe_request_rejects_initial_private_url():
    session = MagicMock()

    with pytest.raises(UnsafeURLError):
        safe_request("GET", "http://127.0.0.1/start", session=session)

    session.request.assert_not_called()
