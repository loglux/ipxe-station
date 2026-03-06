"""API boundary dependency hooks.

This module provides a single boundary point for future cross-cutting API
concerns (authn/authz, rate-limits, request policies) without touching
domain/business logic modules.
"""

from fastapi import Request


def api_boundary_context(request: Request) -> None:
    """Attach a lightweight request marker for centralized API boundary handling."""
    request.state.api_boundary = True
