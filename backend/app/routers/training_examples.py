from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories_training_examples import (
    create_training_example_from_item,
    delete_training_example_for_user,
    export_training_dataset_jsonl,
    get_training_dataset_stats,
    list_training_examples_for_user,
)
from app.schemas import TrainingDatasetStats, TrainingExampleCreateRequest, TrainingExampleRead
from app.security import get_current_user

router = APIRouter(prefix="/api/training-examples", tags=["training-examples"])


@router.post("/{fund_id}/items/{item_id}", response_model=TrainingExampleRead)
def create_from_item(
    fund_id: str,
    item_id: str,
    payload: TrainingExampleCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> TrainingExampleRead:
    try:
        example = create_training_example_from_item(db, fund_id, item_id, current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if example is None:
        raise HTTPException(status_code=404, detail="ФОС или задание не найдено либо нет доступа.")
    return example


@router.get("/", response_model=list[TrainingExampleRead])
def list_examples(
    fund_id: str | None = Query(default=None),
    quality_label: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[TrainingExampleRead]:
    return list_training_examples_for_user(db, current_user, fund_id=fund_id, quality_label=quality_label)


@router.get("/stats", response_model=TrainingDatasetStats)
def dataset_stats(
    fund_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> TrainingDatasetStats:
    return get_training_dataset_stats(db, current_user, fund_id=fund_id)


@router.get("/export/jsonl")
def export_jsonl(
    fund_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> FileResponse:
    file_path = export_training_dataset_jsonl(db, current_user, fund_id=fund_id)
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/jsonl",
    )


@router.delete("/{example_id}", status_code=204)
def delete_example(
    example_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    if not delete_training_example_for_user(db, example_id, current_user):
        raise HTTPException(status_code=404, detail="Обучающий пример не найден или нет доступа.")
    return Response(status_code=204)
