from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.modules.audit.service import record_audit_log
from app.modules.iam import repository as iam_repo
from app.modules.iam.models import User
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
from app.modules.sales.models import SalesmanProfile

_bearer_scheme = HTTPBearer(auto_error=False)


def authenticate_user(db: Session, payload: LoginRequest) -> TokenResponse:
    user = iam_repo.get_user_by_username(db, payload.username)
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        record_audit_log(
            db,
            actor_user_id=user.id if user else None,
            actor_role=user.role.code if user else "ANONYMOUS",
            action="LOGIN_FAILED",
            entity_schema="iam",
            entity_table="users",
            entity_id=user.id if user else 0,
            after_state={"username": payload.username},
            reason="Invalid username/password or inactive account",
        )
        db.commit()
        raise AuthenticationError("Invalid username or password.")

    user.last_login_at = datetime.now(UTC)
    record_audit_log(
        db,
        actor_user_id=user.id,
        actor_role=user.role.code,
        action="LOGIN_SUCCESS",
        entity_schema="iam",
        entity_table="users",
        entity_id=user.id,
        after_state={"username": user.username, "role_code": user.role.code},
    )
    db.commit()

    token = create_access_token(
        user_id=user.id,
        role_code=user.role.code,
        username=user.username,
    )
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role_code=user.role.code,
            role_name=user.role.name,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
        ),
    )


def get_current_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentActor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Authentication credentials were not provided.")

    claims = decode_access_token(credentials.credentials)
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthenticationError("Malformed authentication token subject.") from exc

    user = iam_repo.get_active_user_by_id(db, user_id)
    if user is None:
        raise AuthenticationError("User account is inactive or no longer exists.")

    # Scope PostgreSQL session-local context for defense-in-depth RLS readiness
    db.execute(
        text("SELECT set_config('app.current_user_id', :uid, true), set_config('app.current_role', :role, true)"),
        {"uid": str(user.id), "role": user.role.code},
    )

    return CurrentActor(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role_code=user.role.code,
        role_name=user.role.name,
    )


def require_roles(*allowed_roles: str) -> Callable[[CurrentActor, Session], CurrentActor]:
    def dependency(
        actor: Annotated[CurrentActor, Depends(get_current_actor)],
        db: Annotated[Session, Depends(get_db)],
    ) -> CurrentActor:
        if actor.role_code not in allowed_roles:
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="ACCESS_DENIED",
                entity_schema="iam",
                entity_table="users",
                entity_id=actor.user_id,
                after_state={"required_roles": list(allowed_roles)},
                reason="Role permission mismatch",
            )
            db.commit()
            raise AuthorizationError(
                f"Role '{actor.role_code}' is not permitted to perform this operation."
            )
        return actor

    return dependency


def _to_user_manage_out(u: User) -> UserManageOut:
    return UserManageOut(
        id=u.id,
        username=u.username,
        phone=u.phone,
        full_name=u.full_name,
        role_code=u.role.code,
        role_name=u.role.name,
        is_active=u.is_active,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
    )


def list_all_roles(db: Session) -> list[RoleOut]:
    return [
        RoleOut(id=r.id, code=r.code, name=r.name, description=r.description)
        for r in iam_repo.list_roles(db)
    ]


def list_all_users(db: Session) -> list[UserManageOut]:
    return [_to_user_manage_out(u) for u in iam_repo.list_users(db)]


def create_managed_user(db: Session, actor: CurrentActor, payload: UserCreateRequest) -> UserManageOut:
    uname = payload.username.strip().lower()
    if iam_repo.get_user_by_username(db, uname) is not None:
        raise ConflictError(f"Username '{uname}' already exists.", error_code="DUPLICATE_USERNAME")
    role = iam_repo.get_role_by_code(db, payload.role_code)
    if role is None:
        raise DomainValidationError(f"Invalid role '{payload.role_code}'.")

    phone_clean = payload.phone.strip() if payload.phone and payload.phone.strip() else None
    new_user = User(
        role_id=role.id,
        username=uname,
        phone=phone_clean,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    if role.code == "SALESMAN":
        emp_code = (payload.employee_code or f"SM-{new_user.id:03d}").strip().upper()
        db.add(
            SalesmanProfile(
                user_id=new_user.id,
                employee_code=emp_code,
                territory=payload.territory.strip() if payload.territory else "General Territory",
                is_active=True,
            )
        )
        db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="USER_CREATED",
        entity_schema="iam",
        entity_table="users",
        entity_id=new_user.id,
        after_state={
            "username": new_user.username,
            "full_name": new_user.full_name,
            "role_code": role.code,
            "is_active": True,
        },
        reason=f"Created user {new_user.username} with role {role.code}",
    )
    db.commit()
    reloaded = iam_repo.get_user_by_id(db, new_user.id)
    assert reloaded is not None
    return _to_user_manage_out(reloaded)


def update_managed_user(
    db: Session, actor: CurrentActor, user_id: int, payload: UserUpdateRequest
) -> UserManageOut:
    target = iam_repo.get_user_by_id(db, user_id)
    if target is None:
        raise NotFoundError(f"User {user_id} was not found.")
    if payload.is_active is False and target.id == actor.user_id:
        raise DomainValidationError("You cannot deactivate your own active administrator account.")

    before = {
        "full_name": target.full_name,
        "role_code": target.role.code,
        "is_active": target.is_active,
    }
    actions: list[str] = []
    if payload.role_code is not None and payload.role_code != target.role.code:
        new_role = iam_repo.get_role_by_code(db, payload.role_code)
        if new_role is None:
            raise DomainValidationError(f"Invalid role '{payload.role_code}'.")
        target.role_id = new_role.id
        actions.append("USER_ROLE_CHANGED")
    if payload.is_active is not None and payload.is_active != target.is_active:
        target.is_active = payload.is_active
        actions.append("USER_STATUS_CHANGED")
    if payload.full_name is not None and payload.full_name.strip() != target.full_name:
        target.full_name = payload.full_name.strip()
        if not actions:
            actions.append("USER_PROFILE_UPDATED")

    if not actions:
        return _to_user_manage_out(target)

    db.flush()
    db.refresh(target)
    target = iam_repo.get_user_by_id(db, user_id)
    assert target is not None
    after = {
        "full_name": target.full_name,
        "role_code": target.role.code,
        "is_active": target.is_active,
    }
    for act in actions:
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action=act,
            entity_schema="iam",
            entity_table="users",
            entity_id=target.id,
            before_state=before,
            after_state=after,
            reason=payload.reason,
        )
    db.commit()
    return _to_user_manage_out(target)
