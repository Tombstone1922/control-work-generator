# Narrow generator direction

Ollama is no longer treated as the project core. The target architecture is a narrow-domain FOS generator trained on expert-marked examples collected inside the application.

Implemented in this branch:

- `backend/app/services/narrow_llm_service.py` contains a first narrow generator layer over expert-approved examples.
- `backend/app/routers/narrow_generation.py` exposes a preview endpoint for the narrow generator.
- `backend/app/ml/dataset.py` prepares JSONL examples exported from the application for future model artifacts.
- `backend/.env.example` now uses `NARROW_LLM_*` settings instead of Ollama settings.

Next coding step: connect `narrow_llm` directly into the main item-bank generation endpoint and add a persisted artifact loader for `backend/app/storage/models/narrow_fos_model.json`.
