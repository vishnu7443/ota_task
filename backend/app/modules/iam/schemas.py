from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: int
    username: str
    full_name: str
    role_code: str
    role_name: str
    is_active: bool
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class CurrentActor(BaseModel):
    user_id: int
    username: str
    full_name: str
    role_code: str
    role_name: str
