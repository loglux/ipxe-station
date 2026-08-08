"""API boundary dependency hooks.

This module provides a single boundary point for cross-cutting API concerns
(authn/authz, rate-limits, request policies) without touching domain/business
logic modules.
"""

import hmac

from fastapi import HTTPException, Request

from app.backend.config import settings


def api_boundary_context(request: Request) -> None:
    """Enforce the configured API security mode and mark the request as checked.

    SECURITY_MODE=off (default): no-op, matches the project's trusted-LAN posture.
    SECURITY_MODE=token: requires ``Authorization: Bearer <API_TOKEN>`` on every
    request through this boundary. The frontend's fetchClient already sends this
    header whenever VITE_SECURITY_MODE=token is set.
    """
    request.state.api_boundary = True

    if settings.security_mode != "token":
        return

    if not settings.api_token:
        # Token mode requested but no token configured — fail closed rather than
        # silently behaving like "off".
        raise HTTPException(status_code=500, detail="SECURITY_MODE=token but API_TOKEN is not set")

    auth_header = request.headers.get("authorization", "")
    scheme, _, presented = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    if not hmac.compare_digest(presented, settings.api_token):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
