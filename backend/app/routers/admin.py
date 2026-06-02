from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.routers.auth import user_to_schema
from app.schemas import UserActiveUpdate, UserRead, UserRoleUpdate
from app.security import require_roles

router = APIRouter(prefix="/api/admin", tags=["admin"])
ALLOWED_ROLES = {"teacher", "methodist", "admin"}


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
) -> list[UserRead]:
    users = db.scalars(select(models.User).order_by(models.User.created_at.asc())).all()
    return [user_to_schema(user) for user in users]


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
