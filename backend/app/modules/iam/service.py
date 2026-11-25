from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import create_access_token, decode_access_token, verify_password
from app.modules.audit.service import record_audit_log
from app.modules.iam import repository as iam_repo
from app.modules.iam.schemas import CurrentActor, LoginRequest, TokenResponse, UserPublic

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
