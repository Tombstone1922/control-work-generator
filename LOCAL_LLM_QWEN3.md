# Local Qwen3 integration

The project can optionally use a local OpenAI-compatible LLM server as a pedagogical refiner for generated assessment items.

Recommended model for a 32 GB RAM laptop:

- Qwen3-14B-Instruct GGUF, quantization Q4_K_M or close equivalent.

The model file is not stored in GitHub. Put the downloaded GGUF file into a local folder, for example:

```text
backend/storage/models/qwen3-14b-instruct-q4_k_m.gguf
```

## Run llama.cpp server

Example command:

```powershell
llama-server -m backend/storage/models/qwen3-14b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8081 -c 8192 --jinja
```

If the server build does not support `--jinja`, run without it:

```powershell
llama-server -m backend/storage/models/qwen3-14b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8081 -c 8192
```

## Enable the local LLM in backend

Edit `backend/.env`:

```env
LOCAL_LLM_ENABLED=true
LOCAL_LLM_BASE_URL=http://127.0.0.1:8081/v1
LOCAL_LLM_MODEL=qwen3-14b-instruct-q4_k_m
LOCAL_LLM_TIMEOUT_SECONDS=90
LOCAL_LLM_TEMPERATURE=0.2
LOCAL_LLM_MAX_TOKENS=900
LOCAL_LLM_MAX_ITEMS=24
```

Then restart the backend:

```powershell
cd backend
.\.venv\Scripts\activate
python run.py
```

## Generation pipeline with local LLM

1. The rule/context generator creates assessment items from RPD topics and the discipline knowledge catalog.
2. The narrow generator uses OM corpus and teacher-approved examples.
3. The local LLM refiner improves a limited number of generated items using discipline context.
4. The postprocessor removes noisy fragments, rebuilds generic items and enforces uniqueness.
5. The validator checks topic coverage, competency coverage, answers, criteria and strong duplicates.

The backend does not fail if the local LLM server is unavailable. It simply keeps the base generated items and adds a warning when refinement fails.
