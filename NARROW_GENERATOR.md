# Narrow FOS generator direction

Ollama is no longer treated as the project core. The target architecture is a narrow-domain FOS generator trained on expert-marked examples, a reference corpus of ready assessment materials, and a dynamic catalog of real disciplines extracted from RPD archives.

## Implemented

- `backend/app/services/narrow_llm_service.py` contains the narrow generator layer.
- `backend/app/ml/narrow_fos_model.py` contains a local trainable model artifact with TF-IDF index, weighted retrieval, assessment-type matching and example adaptation.
- `backend/app/tools/train_narrow_fos_model.py` trains `storage/models/narrow_fos_model.json` from JSONL examples.
- `backend/app/services/om_reference_extractor.py` extracts reusable examples from ready OM/FOS documents.
- `backend/app/tools/build_om_corpus.py` builds `storage/om_corpus/om_examples.jsonl` from a ZIP archive or folder with PDF/DOCX/TXT files.
- `backend/app/services/discipline_catalog.py` enriches weak RPD analysis with a dynamic discipline catalog.
- `backend/app/tools/build_discipline_catalog.py` builds `storage/discipline_catalog/discipline_profiles.json` from a ZIP archive or folder with RPD files.
- `backend/app/routers/narrow_generation.py` exposes a preview endpoint for the narrow generator.
- `backend/.env.example` uses `NARROW_LLM_*`, `OM_CORPUS_PATH` and `DISCIPLINE_CATALOG_PATH` settings instead of Ollama settings.

## Training workflow

Step 1. Build dynamic discipline catalog from RPD archive:

```bash
cd backend
python -m app.tools.build_discipline_catalog path/to/RPD_archive.zip --output storage/discipline_catalog/discipline_profiles.json
```

Step 2. Build OM corpus:

```bash
python -m app.tools.build_om_corpus path/to/OM_archive.zip --output storage/om_corpus/om_examples.jsonl
```

Step 3. Train local narrow model:

```bash
python -m app.tools.train_narrow_fos_model --om-corpus storage/om_corpus/om_examples.jsonl --output storage/models/narrow_fos_model.json
```

Step 4. Run backend:

```bash
python run.py
```

Optional teacher feedback can be added with another `--training-dataset` argument pointing to exported JSONL from the application.

After that, the `narrow_llm` generation mode will use the trained local model artifact first, then expert-approved examples, then examples extracted from ready OM/FOS documents, then template fallback. Weak or short RPD documents will also be enriched through the dynamic discipline catalog.

## Target generation pipeline

RPD archive -> dynamic discipline catalog -> current RPD analysis -> FOS structure -> planned assessment items -> trained narrow FOS model -> teacher review -> training examples -> updated model artifact -> DOCX export.

## Important limitation

This is a local trainable narrow-domain generator, not a general neural LLM with billions of parameters. It is intentionally lightweight for MVP and closed-contour deployment: it learns from RPD/OM/FOS examples, stores its own knowledge base, ranks relevant examples and adapts them to the target discipline, topic, competency and assessment type.
