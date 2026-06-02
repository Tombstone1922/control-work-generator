from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import AuthResponse, UserCreate, UserLogin, UserRead
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_to_schema(user: models.User) -> UserRead:
    return UserRead(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/register", response_model=AuthResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> AuthResponse:
    existing_user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует.")

    user = models.User(
        id=str(uuid4()),
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role="teacher",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(access_token=create_access_token(user), user=user_to_schema(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован.")

    return AuthResponse(access_token=create_access_token(user), user=user_to_schema(user))


@router.get("/me", response_model=UserRead)
def me(current_user: models.User = Depends(get_current_user)) -> UserRead:
    return user_to_schema(current_user)
