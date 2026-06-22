$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$BackendDir = Join-Path $ProjectRoot "backend"
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"

Write-Host "Checking llama-server models endpoint..." -ForegroundColor Cyan
try {
    Invoke-RestMethod http://127.0.0.1:8081/v1/models | ConvertTo-Json -Depth 10
} catch {
    Write-Host "llama-server is not available on http://127.0.0.1:8081" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

if (!(Test-Path $BackendDir)) {
    Write-Host "Backend folder not found: $BackendDir" -ForegroundColor Red
    exit 1
}

Set-Location $BackendDir
if (Test-Path $VenvActivate) {
    . $VenvActivate
    Write-Host "Running backend local LLM diagnostic..." -ForegroundColor Cyan
    python -m app.tools.test_local_llm
} else {
    Write-Host "Backend .venv not found. Start backend once or create .venv first." -ForegroundColor Yellow
}
