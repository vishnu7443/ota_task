from datetime import datetime

from pydantic import BaseModel, Field, field_validator


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


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None


class UserManageOut(BaseModel):
    id: int
    username: str
    phone: str | None = None
    full_name: str
    role_code: str
    role_name: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    role_code: str = Field(
        pattern=r"^(SALESMAN|FACTORY_ADMIN|PRODUCTION_SUPERVISOR|ACCOUNTANT_AUDITOR|OWNER)$"
    )
    password: str = Field(min_length=8, max_length=128)
    employee_code: str | None = Field(default=None, max_length=32)
    territory: str | None = Field(default=None, max_length=80)


class UserUpdateRequest(BaseModel):
    role_code: str | None = Field(
        default=None,
        pattern=r"^(SALESMAN|FACTORY_ADMIN|PRODUCTION_SUPERVISOR|ACCOUNTANT_AUDITOR|OWNER)$",
    )
    is_active: bool | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s
