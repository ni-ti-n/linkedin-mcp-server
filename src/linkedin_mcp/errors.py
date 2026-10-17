"""Error types surfaced to the MCP client as readable messages."""

from __future__ import annotations

import functools
import inspect
import typing
from typing import Any, Awaitable, Callable


class LinkedInError(Exception):
    """Base class for all errors returned to the MCP client."""


class AuthError(LinkedInError):
    """Missing / invalid / expired credentials."""


class ScopeError(LinkedInError):
    """The call requires a scope the current token was not granted.

    Raised for Tier-2 (partner-approved) features so the user gets a clear,
    actionable message instead of an opaque 403. Carries the HTTP status and
    LinkedIn response body so the surfaced payload is fully debuggable.
    """

    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        self.status = status
        self.body = body
        super().__init__(message)


class APIError(LinkedInError):
    """A non-2xx response from the LinkedIn REST API."""

    def __init__(self, status: int, message: str, body: str | None = None):
        self.status = status
        self.body = body
        super().__init__(message)


def error_payload(exc: LinkedInError) -> dict[str, Any]:
    """Turn a LinkedInError into a structured, debuggable result dict.

    The MCP dispatch layer would otherwise swallow the exception into an opaque
    ``"Error executing tool <name>"`` string with no HTTP status or API body.
    Returning this dict instead surfaces the real cause to the MCP client.
    """
    payload: dict[str, Any] = {
        "error": type(exc).__name__,
        "message": str(exc),
    }
    status = getattr(exc, "status", None)
    body = getattr(exc, "body", None)
    if status is not None:
        payload["status"] = status
    if body:
        payload["linkedin_response"] = body
    if isinstance(exc, ScopeError):
        payload["hint"] = (
            "This endpoint is part of LinkedIn's Community Management Platform "
            "and needs a partner-approved scope, not plain w_member_social. "
            "See the tool docstring for the exact permission required."
        )
    return payload


def tool_safe(
    fn: Callable[..., Awaitable[dict]],
) -> Callable[..., Awaitable[dict]]:
    """Wrap an async MCP tool so a LinkedInError becomes a structured dict.

    Any other exception still propagates (a real bug should not be masked as a
    tidy error payload). Preserves the signature and resolves the original
    function's type hints to concrete objects, so the MCP SDK's Pydantic schema
    builder does not need to re-resolve string annotations (``Literal[...]`` etc.)
    against this module's globals — which ``from __future__ import annotations``
    would otherwise require.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict:
        try:
            return await fn(*args, **kwargs)
        except LinkedInError as exc:
            return error_payload(exc)

    # Resolve annotations in the ORIGINAL function's module namespace, then stash
    # the concrete objects on the wrapper. inspect.signature(eval_str=True) and
    # the resulting __annotations__ no longer depend on this module's globals.
    try:
        hints = typing.get_type_hints(fn)
        wrapper.__annotations__ = hints
        wrapper.__signature__ = inspect.signature(fn, eval_str=True)  # type: ignore[attr-defined]
    except Exception:
        # Fall back to the raw signature; schema may be looser but tool works.
        wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
    return wrapper
