"""
Authentication & authorization utilities.

For this project we use simple API-key authentication:
the client sends `X-API-Key: <key>` in the request header,
and we check it against the list configured in .env.

When you're ready to add user accounts, you can extend this file
with JWT token creation/verification using `python-jose`.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from typing import Optional

from backend.app.core.config import settings


# ─── Header scheme ────────────────────────────────────────────────────
# This tells FastAPI / Swagger UI that the API expects an X-API-Key header.
# `auto_error=False` means we handle the "missing header" case ourselves
# so we can return our own friendly 401 message.
api_key_header_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Your API key (configured in the server's .env file)."
)


# ─── Data class for the "current user" ────────────────────────────────
class APIUser:
    """
    Lightweight stand-in for an authenticated user.

    In a full system this would have id, email, roles, etc.
    For our API-key setup, the "user" is identified by the key itself.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        # In the future: look up the key in the DB and attach a real user ID
        self.id = api_key
        self.is_authenticated = True

    def __repr__(self) -> str:
        # Don't leak the full key in logs
        masked = f"{self.api_key[:4]}***{self.api_key[-2:]}" if len(self.api_key) > 6 else "***"
        return f"<APIUser key={masked}>"


# ─── The dependency routers will use ──────────────────────────────────
async def get_current_user(
    api_key: Optional[str] = Depends(api_key_header_scheme),
) -> APIUser:
    """
    FastAPI dependency that validates the X-API-Key header.

    Usage in a router:
        @router.get("/experiments", dependencies=[Depends(get_current_user)])
        def list_experiments(): ...

    Raises:
        HTTPException 401 if the header is missing or the key is invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide it in the 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key not in settings.api_keys_list:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return APIUser(api_key=api_key)
