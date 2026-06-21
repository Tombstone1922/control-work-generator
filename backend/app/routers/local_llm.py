from fastapi import APIRouter, Depends

from app import models
from app.security import get_current_user
from app.services.local_llm_diagnostics import check_local_llm, generate_local_llm_sample_task

router = APIRouter(prefix="/api/local-llm", tags=["local-llm"])


@router.get("/status")
def local_llm_status(current_user: models.User = Depends(get_current_user)) -> dict:
    return check_local_llm().as_dict()


@router.post("/test")
def local_llm_test(current_user: models.User = Depends(get_current_user)) -> dict:
    return generate_local_llm_sample_task()
