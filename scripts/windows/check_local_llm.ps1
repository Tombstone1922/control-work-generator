$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$BackendDir = Join-Path $ProjectRoot "backend"
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"

Write-Host "Checking default Qwen3 14B endpoint on 8081..." -ForegroundColor Cyan
try {
    Invoke-RestMethod http://127.0.0.1:8081/v1/models | ConvertTo-Json -Depth 10
} catch {
    Write-Host "llama-server is not available on http://127.0.0.1:8081" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host "Checking Qwen3 8B endpoint on 8083..." -ForegroundColor Cyan
try {
    Invoke-RestMethod http://127.0.0.1:8083/v1/models | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Qwen3 8B llama-server is not available on http://127.0.0.1:8083" -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

Write-Host "Checking experimental Qwen3.5 9B endpoint on 8082..." -ForegroundColor Cyan
try {
    Invoke-RestMethod http://127.0.0.1:8082/v1/models | ConvertTo-Json -Depth 10
} catch {
    Write-Host "experimental llama-server is not available on http://127.0.0.1:8082" -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

if (!(Test-Path $BackendDir)) {
    Write-Host "Backend folder not found: $BackendDir" -ForegroundColor Red
    exit 1
}

Set-Location $BackendDir
if (Test-Path $VenvActivate) {
    . $VenvActivate
    Write-Host "Running backend local LLM diagnostic for default profile..." -ForegroundColor Cyan
    python -m app.tools.test_local_llm
    Write-Host "Running backend local LLM diagnostic for Qwen3 8B profile..." -ForegroundColor Cyan
    python -m app.tools.test_local_llm qwen3_8b
    Write-Host "Running backend local LLM diagnostic for Qwen3.5 9B profile..." -ForegroundColor Cyan
    python -m app.tools.test_local_llm qwen35_9b
} else {
    Write-Host "Backend .venv not found. Start backend once or create .venv first." -ForegroundColor Yellow
}
