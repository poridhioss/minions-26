"""
Custom exceptions raised by the SDK.

We map backend HTTP status codes to typed exceptions so callers can do::

    try:
        mltracker.experiments.get(999)
    except mltracker.NotFoundError:
        ...
    except mltracker.AuthenticationError:
        ...

All exceptions inherit from :class:`MLTrackerError` so a single ``except``
clause catches the whole family.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


class MLTrackerError(Exception):
    """Base class for every error raised by the SDK."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body

    def __str__(self) -> str:
        return self.message


class AuthenticationError(MLTrackerError):
    """Raised on HTTP 401 — missing or invalid ``X-API-Key``."""


class NotFoundError(MLTrackerError):
    """Raised on HTTP 404 — the requested resource doesn't exist."""


class ValidationError(MLTrackerError):
    """Raised on HTTP 400 / 422 — request body or query string is invalid."""


class APIError(MLTrackerError):
    """Raised on any other non-2xx response (5xx, unexpected 4xx, etc)."""


# Map status code → exception class. Used by ``client._raise_for_status``.
_STATUS_MAP: dict[int, type[MLTrackerError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: AuthenticationError,  # we don't really use 403, but treat it like 401
    404: NotFoundError,
    409: ValidationError,      # conflict (e.g. duplicate name) → caller sees ValidationError
    422: ValidationError,
}


def exception_for_status(status_code: int) -> type[MLTrackerError]:
    """Return the exception class appropriate for ``status_code``."""
    return _STATUS_MAP.get(status_code, APIError)


def _extract_detail(body: Any) -> str:
    """
    FastAPI always returns a JSON body with a ``detail`` field on errors.
    Pull a useful human message out of the body, regardless of shape.
    """
    if body is None:
        return ""
    if isinstance(body, Mapping):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            # 422 from Pydantic: list of {loc, msg, type}
            return "; ".join(
                f"{'.'.join(str(p) for p in item.get('loc', []))}: {item.get('msg', '')}"
                for item in detail
                if isinstance(item, Mapping)
            )
        if detail is not None:
            return str(detail)
    if isinstance(body, str):
        return body
    return ""
