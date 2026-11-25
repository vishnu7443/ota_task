from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.modules.iam.models import CompanyProfile, Role, User


def get_user_by_username(db: Session, username: str) -> User | None:
    stmt = (
        select(User)
        .options(joinedload(User.role))
        .where(User.username == username.strip())
    )
    return db.execute(stmt).scalar_one_or_none()


def get_active_user_by_id(db: Session, user_id: int) -> User | None:
    stmt = (
        select(User)
        .options(joinedload(User.role))
        .where(User.id == user_id, User.is_active.is_(True))
    )
    return db.execute(stmt).scalar_one_or_none()


def get_role_by_code(db: Session, code: str) -> Role | None:
    return db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()


def get_company_profile(db: Session) -> CompanyProfile | None:
    return db.execute(select(CompanyProfile).limit(1)).scalar_one_or_none()
