from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.core.dependencies import Principal, require_role
from app.core.security import (
    create_access_token,
    generate_api_key,
    hash_password,
    verify_password,
)
from app.database.session import get_db
from app.models.models import ApiKey
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_username(payload.username)

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    role_name = await repo.get_role_name(user.role_id)
    token = create_access_token(subject=user.username, role=role_name or "viewer")
    return TokenResponse(access_token=token, expires_in_minutes=settings.api_access_token_expire_minutes)


@router.post("/register", response_model=UserOut, status_code=201)
async def register_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("admin")),
):
    """Only an existing admin can provision new users."""
    repo = UserRepository(db)
    if await repo.get_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already taken")

    user = await repo.create(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role_name=payload.role,
    )
    return user


@router.get("/me", response_model=UserOut)
async def whoami(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
):
    repo = UserRepository(db)
    user = await repo.get_by_username(principal.subject)
    if user is None:
        raise HTTPException(status_code=404, detail="Authenticated principal has no matching user record (are you using an API key?)")
    return user


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("admin")),
):
    raw_key, key_hash = generate_api_key()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days
        else None
    )
    api_key = ApiKey(
        name=payload.name,
        key_hash=key_hash,
        role=payload.role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreated(
        id=api_key.id, name=api_key.name, role=api_key.role,
        api_key=raw_key, expires_at=api_key.expires_at,
    )


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("admin")),
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.is_active = False
    await db.commit()
