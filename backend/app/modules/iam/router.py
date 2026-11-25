from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import repository as iam_repo
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import (
    CurrentActor,
    LoginRequest,
    RoleOut,
    TokenResponse,
    UserCreateRequest,
    UserManageOut,
    UserPublic,
    UserUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/iam", tags=["IAM User & Role Governance"])

_UserViewer = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR")),
]
_UserManager = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "OWNER")),
]


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    return iam_service.authenticate_user(db, payload)


@router.get("/me", response_model=UserPublic)
def get_me(
    actor: Annotated[CurrentActor, Depends(iam_service.get_current_actor)],
    db: Annotated[Session, Depends(get_db)],
) -> UserPublic:
    user = iam_repo.get_active_user_by_id(db, actor.user_id)
    assert user is not None
    return UserPublic(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role_code=user.role.code,
        role_name=user.role.name,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


@users_router.get("/roles", response_model=list[RoleOut])
def list_roles(_actor: _UserViewer, db: Annotated[Session, Depends(get_db)]) -> list[RoleOut]:
    return iam_service.list_all_roles(db)


@users_router.get("/users", response_model=list[UserManageOut])
def list_users(_actor: _UserViewer, db: Annotated[Session, Depends(get_db)]) -> list[UserManageOut]:
    return iam_service.list_all_users(db)


@users_router.post("/users", response_model=UserManageOut, status_code=201)
def create_user(
    payload: UserCreateRequest,
    actor: _UserManager,
    db: Annotated[Session, Depends(get_db)],
) -> UserManageOut:
    return iam_service.create_managed_user(db, actor, payload)


@users_router.patch("/users/{user_id}", response_model=UserManageOut)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    actor: _UserManager,
    db: Annotated[Session, Depends(get_db)],
) -> UserManageOut:
    return iam_service.update_managed_user(db, actor, user_id, payload)
