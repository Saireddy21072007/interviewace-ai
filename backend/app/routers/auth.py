"""
Authentication: POST /register, POST /login, and the /me endpoints.

The paths are exactly the ones in the project guide's REST API table, so the
contract in the report and the contract in the code are the same thing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import User, utcnow
from ..schemas import (
    LoginRequest, PasswordChange, RegisterRequest, TokenResponse, UserOut, UserUpdate,
)
from ..security import create_access_token, hash_password, password_problems, verify_password

router = APIRouter(tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    """Create an account and sign the user straight in.

    Returning a token here rather than making the client immediately call
    /login removes a whole round trip and a whole class of "registered but not
    logged in" states in the frontend.
    """
    email = payload.email.lower().strip()

    problems = password_problems(payload.password)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" ".join(problems))

    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Try signing in instead.",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        target_role=payload.target_role,
        experience_level=payload.experience_level,
        # The single bootstrap admin is configured in .env, not hardcoded and
        # not self-service - otherwise anyone could register as an admin.
        role="admin" if email == settings.admin_email.lower().strip() else "user",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _token_for(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower().strip()))

    # Same message and roughly the same work whether the email exists or not,
    # so the endpoint cannot be used to enumerate registered accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This account has been disabled.")

    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.get("/me", response_model=UserOut, tags=["auth"])
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut, tags=["auth"])
def update_me(payload: UserUpdate, user: CurrentUser, db: DbSession) -> User:
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


# response_model=None is required on 204 routes: `from __future__ import
# annotations` turns the `-> None` return hint into a string that FastAPI
# resolves back to the NoneType *class*, which it then treats as a real
# response model - and a 204 is not allowed to have a body.
@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT,
             response_model=None, tags=["auth"])
def change_password(payload: PasswordChange, user: CurrentUser, db: DbSession) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Current password is incorrect.")
    problems = password_problems(payload.new_password)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" ".join(problems))

    user.password_hash = hash_password(payload.new_password)
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT,
               response_model=None, tags=["auth"])
def delete_me(user: CurrentUser, db: DbSession) -> None:
    """Delete the account and everything attached to it.

    Cascades remove resumes, interviews, transcripts and reports. A product
    that records someone's voice has to be able to forget them completely.
    """
    db.delete(user)
    db.commit()


def _token_for(user: User) -> TokenResponse:
    token = create_access_token(user.id, {"role": user.role, "email": user.email})
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        user=UserOut.model_validate(user),
    )
