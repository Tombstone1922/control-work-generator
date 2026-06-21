# Narrow FOS generator direction

Ollama is no longer treated as the project core. The target architecture is a narrow-domain FOS generator trained on expert-marked examples and on a reference corpus of ready assessment materials (OM/FOS documents).

## Implemented

- `backend/app/services/narrow_llm_service.py` contains the narrow generator layer.
- `backend/app/services/om_reference_extractor.py` extracts reusable examples from ready OM/FOS documents.
- `backend/app/tools/build_om_corpus.py` builds `storage/om_corpus/om_examples.jsonl` from a ZIP archive or folder with PDF/DOCX/TXT files.
- `backend/app/routers/narrow_generation.py` exposes a preview endpoint for the narrow generator.
- `backend/app/ml/dataset.py` prepares JSONL examples exported from the application for future model artifacts.
- `backend/.env.example` uses `NARROW_LLM_*` and `OM_CORPUS_PATH` settings instead of Ollama settings.

## OM corpus workflow

```bash
cd backend
python -m app.tools.build_om_corpus path/to/OM_archive.zip --output storage/om_corpus/om_examples.jsonl
python run.py
```

After that, the `narrow_llm` generation mode will use:

1. expert-approved examples saved by a teacher inside the application;
2. examples extracted from ready OM/FOS documents;
3. template fallback if there are not enough examples.

## Target generation pipeline

RPD analysis -> FOS structure -> planned assessment items -> narrow generator over OM corpus -> teacher review -> training examples -> updated corpus/model artifact -> DOCX export.
