$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$BackendDir = Join-Path $ProjectRoot "backend"
$EnvPath = Join-Path $BackendDir ".env"
$EnvExamplePath = Join-Path $BackendDir ".env.example"
$ModelsDir = Join-Path $BackendDir "storage\models"

if (!(Test-Path $ProjectRoot)) {
    Write-Host "Project folder not found: $ProjectRoot" -ForegroundColor Red
    exit 1
}

if (!(Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    Write-Host "Created models folder: $ModelsDir" -ForegroundColor Green
}

if (!(Test-Path $EnvPath)) {
    if (Test-Path $EnvExamplePath) {
        Copy-Item $EnvExamplePath $EnvPath
        Write-Host "Created .env from .env.example" -ForegroundColor Green
    } else {
        New-Item -ItemType File -Force -Path $EnvPath | Out-Null
        Write-Host "Created empty .env" -ForegroundColor Green
    }
}

$envContent = Get-Content $EnvPath -Raw
$settings = @{
    "NARROW_LLM_MODEL_PATH" = "storage/models/narrow_fos_model.json"
    "OM_CORPUS_PATH" = "storage/om_corpus/om_examples.jsonl"
    "DISCIPLINE_CATALOG_PATH" = "storage/discipline_catalog/discipline_profiles.json"
    "LOCAL_LLM_ENABLED" = "true"
    "LOCAL_LLM_BASE_URL" = "http://127.0.0.1:8081/v1"
    "LOCAL_LLM_MODEL" = "qwen3-14b-instruct-q4_k_m"
    "LOCAL_LLM_TIMEOUT_SECONDS" = "90"
    "LOCAL_LLM_TEMPERATURE" = "0.2"
    "LOCAL_LLM_MAX_TOKENS" = "650"
    "LOCAL_LLM_MAX_ITEMS" = "10"
    "LOCAL_LLM_REFINEMENT_MODE" = "single"
    "LOCAL_LLM_BATCH_SIZE" = "4"
    "LOCAL_LLM_FORCE_REWRITE" = "false"
    "LOCAL_LLM_SKIP_TYPES" = "oral,exam_questions,credit,test_bank,diagnostic"
    "LOCAL_LLM_QWEN35_ENABLED" = "true"
    "LOCAL_LLM_QWEN35_BASE_URL" = "http://127.0.0.1:8082/v1"
    "LOCAL_LLM_QWEN35_MODEL" = "qwen35-9b-gemini-reasoning-distill-q4_k_m"
    "LOCAL_LLM_QWEN35_TIMEOUT_SECONDS" = "120"
    "LOCAL_LLM_QWEN35_TEMPERATURE" = "0.2"
    "LOCAL_LLM_QWEN35_MAX_TOKENS" = "1800"
}

foreach ($key in $settings.Keys) {
    $value = $settings[$key]
    if ($envContent -match "(?m)^$key=") {
        $envContent = [regex]::Replace($envContent, "(?m)^$key=.*$", "$key=$value")
    } else {
        if (!$envContent.EndsWith("`n")) { $envContent += "`n" }
        $envContent += "$key=$value`n"
    }
}

Set-Content -Path $EnvPath -Value $envContent -Encoding UTF8

Write-Host "Configured backend .env for local LLM refinement: $ProjectRoot" -ForegroundColor Green
Write-Host "Default model: Qwen3 14B on http://127.0.0.1:8081/v1" -ForegroundColor Yellow
Write-Host "Experimental model: Qwen3.5 9B on http://127.0.0.1:8082/v1" -ForegroundColor Yellow
Write-Host "Put GGUF models here:" -ForegroundColor Cyan
Write-Host "  $ModelsDir" -ForegroundColor Cyan
