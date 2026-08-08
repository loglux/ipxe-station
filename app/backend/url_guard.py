"""SSRF guard for endpoints that fetch user-supplied URLs.

Used by app/routes/assets.py's download and check-url endpoints. Blocks
requests to loopback, link-local, private, reserved, multicast, and
unspecified addresses, and provides a helper to validate redirect targets the
same way — so a URL that passes the initial check can't smuggle a request to
an internal service via a 3xx response.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5


class UnsafeURLError(ValueError):
    """Raised when a URL resolves to a non-public or otherwise disallowed target."""


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeURLError(f"Could not parse resolved address: {address}") from exc
    return not (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_public_http_url(url: str) -> None:
    """Raise UnsafeURLError unless url is http(s) and resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Only {'/'.join(sorted(ALLOWED_SCHEMES))} URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL has no hostname")

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve host: {hostname}") from exc

    if not addr_infos:
        raise UnsafeURLError(f"Could not resolve host: {hostname}")

    for family, _, _, _, sockaddr in addr_infos:
        address = sockaddr[0]
        if not _is_public_address(address):
            raise UnsafeURLError(f"URL resolves to a non-public address: {address}")


def safe_request(
    method: str, url: str, *, session: requests.Session = None, **kwargs
) -> requests.Response:
    """Like requests.request, but validates the URL and every redirect hop.

    Redirects are followed manually (allow_redirects is forced off internally) so
    each hop is re-validated with assert_public_http_url before being requested —
    a URL that passes the initial check can't be used to smuggle a request to a
    private/loopback target via a 3xx response.
    """
    sess = session or requests
    kwargs.pop("allow_redirects", None)
    current_url = url

    for _ in range(MAX_REDIRECTS + 1):
        assert_public_http_url(current_url)
        resp = sess.request(method, current_url, allow_redirects=False, **kwargs)

        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise UnsafeURLError("Redirect response missing Location header")
            current_url = urljoin(current_url, location)
            continue

        return resp

    raise UnsafeURLError("Too many redirects")
