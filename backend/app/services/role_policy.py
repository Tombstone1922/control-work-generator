from fastapi import HTTPException, status

from app import models

REVIEWER_ROLES = {"methodist", "admin"}
CONTENT_EDITOR_ROLES = {"teacher", "admin"}
TEACHER_EDITABLE_FUND_STATUSES = {"draft", "generated", "revision_required"}
TEACHER_EDITABLE_GENERATION_STATUSES = {"generated", "revision_required"}
TEACHER_ALLOWED_REVIEW_STATUSES = {"generated", "in_review"}
REVIEWER_ALLOWED_STATUSES = {"in_review", "revision_required", "approved"}


def is_admin(user: models.User) -> bool:
    return user.role == "admin"


def is_teacher(user: models.User) -> bool:
    return user.role == "teacher"


def is_reviewer(user: models.User) -> bool:
    return user.role in REVIEWER_ROLES


def user_owns_program(user: models.User, program: models.Program | None) -> bool:
    return program is not None and program.owner_user_id in {None, user.id}


def require_teacher_or_admin(user: models.User) -> None:
    if user.role not in CONTENT_EDITOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Действие доступно преподавателю-владельцу или администратору.",
        )


def ensure_can_edit_program_content(user: models.User, program: models.Program | None, status_value: str = "draft") -> None:
    if is_admin(user):
        return
    if not is_teacher(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Методист проверяет и утверждает материалы, но не редактирует рабочие материалы преподавателя.",
        )
    if not user_owns_program(user, program):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Преподаватель может редактировать только свои материалы.",
        )
    if status_value not in TEACHER_EDITABLE_FUND_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Материал находится на проверке или уже утвержден. Редактирование недоступно.",
        )


def ensure_can_edit_fund_content(user: models.User, fund: models.AssessmentFund | None) -> None:
    if fund is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ФОС не найден или нет доступа.")
    ensure_can_edit_program_content(user, fund.program, fund.status)


def ensure_can_edit_generation_content(
    user: models.User,
    generation: models.GenerationSession | None,
    program: models.Program | None,
) -> None:
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сеанс генерации не найден или нет доступа.")
    if is_admin(user):
        return
    if not is_teacher(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Методист проверяет и утверждает материалы, но не редактирует задания преподавателя.",
        )
    if not user_owns_program(user, program):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Преподаватель может редактировать только свои материалы.",
        )
    if generation.status not in TEACHER_EDITABLE_GENERATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Работа находится на проверке или уже утверждена. Редактирование недоступно.",
        )


def ensure_can_review(user: models.User) -> None:
    if not is_reviewer(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Проверка и утверждение доступны методисту или администратору.",
        )


def validate_fund_status_transition(user: models.User, status_value: str) -> None:
    if is_admin(user):
        return
    if is_teacher(user):
        if status_value not in TEACHER_ALLOWED_REVIEW_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Преподаватель может сохранить черновик или отправить ФОС на проверку, но не утверждать его.",
            )
        return
    if is_reviewer(user):
        if status_value not in REVIEWER_ALLOWED_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Методист может принять материал в проверку, вернуть на доработку или утвердить.",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для изменения статуса.")
