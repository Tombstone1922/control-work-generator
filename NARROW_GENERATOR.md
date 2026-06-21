# Narrow FOS generator direction

Ollama is no longer treated as the project core. The target architecture is a narrow-domain FOS generator trained on expert-marked examples and on a reference corpus of ready assessment materials.

## Implemented

- `backend/app/services/narrow_llm_service.py` contains the narrow generator layer.
- `backend/app/ml/narrow_fos_model.py` contains a local trainable model artifact with TF-IDF index, weighted retrieval, assessment-type matching and example adaptation.
- `backend/app/tools/train_narrow_fos_model.py` trains `storage/models/narrow_fos_model.json` from JSONL examples.
- `backend/app/services/om_reference_extractor.py` extracts reusable examples from ready OM/FOS documents.
- `backend/app/tools/build_om_corpus.py` builds `storage/om_corpus/om_examples.jsonl` from a ZIP archive or folder with PDF/DOCX/TXT files.
- `backend/app/routers/narrow_generation.py` exposes a preview endpoint for the narrow generator.
- `backend/.env.example` uses `NARROW_LLM_*` and `OM_CORPUS_PATH` settings instead of Ollama settings.

## Training workflow

Step 1. Build OM corpus:

```bash
cd backend
python -m app.tools.build_om_corpus path/to/OM_archive.zip --output storage/om_corpus/om_examples.jsonl
```

Step 2. Train local narrow model:

```bash
python -m app.tools.train_narrow_fos_model --om-corpus storage/om_corpus/om_examples.jsonl --output storage/models/narrow_fos_model.json
```

Step 3. Run backend:

```bash
python run.py
```

Optional teacher feedback can be added with another `--training-dataset` argument pointing to exported JSONL from the application.

After that, the `narrow_llm` generation mode will use the trained local model artifact first, then expert-approved examples, then examples extracted from ready OM/FOS documents, then template fallback.

## Target generation pipeline

RPD analysis -> FOS structure -> planned assessment items -> trained narrow FOS model -> teacher review -> training examples -> updated model artifact -> DOCX export.

## Important limitation

This is a local trainable narrow-domain generator, not a general neural LLM with billions of parameters. It is intentionally lightweight for MVP and closed-contour deployment: it learns from OM/FOS examples, stores its own knowledge base, ranks relevant examples and adapts them to the target discipline, topic, competency and assessment type.
