from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="viewer", pattern="^(admin|operator|viewer)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime


class ApiKeyCreate(BaseModel):
    name: str
    role: str = Field(default="viewer", pattern="^(admin|operator|viewer)$")
    expires_in_days: int | None = None


class ApiKeyCreated(BaseModel):
    id: int
    name: str
    role: str
    api_key: str  # shown once, at creation time only
    expires_at: datetime | None
