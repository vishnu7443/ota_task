from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import repository as iam_repo
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor, LoginRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["Authentication"])


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
