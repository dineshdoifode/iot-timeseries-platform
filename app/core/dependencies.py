"""
Auth dependencies for FastAPI routes.

Two supported credentials:
  - `Authorization: Bearer <jwt>`  — human users, obtained via /api/v1/auth/login
  - `X-API-Key: <raw key>`         — service-to-service (provisioning scripts, CI)

Both resolve to a (subject, role) pair used by `require_role(...)`.
"""

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, hash_api_key
from app.database.session import get_db
from app.models.models import ApiKey

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {"viewer": 0, "operator": 1, "admin": 2}


@dataclass
class Principal:
    subject: str      # username or api-key name
    role: str
    auth_method: str  # "jwt" | "api_key"


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if credentials is not None:
        try:
            payload = decode_access_token(credentials.credentials)
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {exc}",
            ) from exc
        return Principal(subject=payload["sub"], role=payload["role"], auth_method="jwt")

    if x_api_key is not None:
        key_hash = hash_api_key(x_api_key)
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return Principal(subject=api_key.name, role=api_key.role, auth_method="api_key")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing credentials — provide a Bearer token or X-API-Key header",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(minimum_role: str):
    """Usage: Depends(require_role("operator")) — admin > operator > viewer."""

    async def checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if ROLE_HIERARCHY.get(principal.role, -1) < ROLE_HIERARCHY.get(minimum_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{minimum_role}' or higher (you have '{principal.role}')",
            )
        return principal

    return checker
