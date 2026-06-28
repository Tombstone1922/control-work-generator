from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import select

from app import models
from app.database import get_db
from app.routers.auth import apply_user_profile_update, user_to_schema
from app.schemas import UserActiveUpdate, UserProfileUpdate, UserRead, UserRoleUpdate
from app.security import hash_password, require_roles

router = APIRouter(prefix="/api/admin", tags=["admin"])
ALLOWED_ROLES = {"teacher", "methodist", "admin"}


class AdminUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = "teacher"


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
) -> list[UserRead]:
    users = db.scalars(select(models.User).order_by(models.User.created_at.asc())).all()
    return [user_to_schema(user) for user in users]


@router.post("/users", response_model=UserRead)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
) -> UserRead:
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Недопустимая роль пользователя.")

    email = str(payload.email).lower()
    existing_user = db.scalar(select(models.User).where(models.User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует.")

    user = models.User(
        id=str(uuid4()),
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_schema(user)


@router.patch("/users/{user_id}/profile", response_model=UserRead)
def update_user_profile(
    user_id: str,
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
) -> UserRead:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")

    apply_user_profile_update(user, payload, db, exclude_user_id=user.id)
    db.commit()
    db.refresh(user)
    return user_to_schema(user)


@router.patch("/users/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles("admin")),
) -> UserRead:
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Недопустимая роль пользователя.")

    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    if user.id == current_user.id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Нельзя снять роль администратора у текущего пользователя.")

    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user_to_schema(user)


@router.patch("/users/{user_id}/active", response_model=UserRead)
def update_user_activity(
    user_id: str,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles("admin")),
) -> UserRead:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать текущего пользователя.")

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user_to_schema(user)
