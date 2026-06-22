$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$ModelPath = Join-Path $ProjectRoot "backend\storage\models\Qwen3-14B-Q4_K_M.gguf"

if (!(Test-Path $ModelPath)) {
    Write-Host "Model file not found:" -ForegroundColor Red
    Write-Host "  $ModelPath" -ForegroundColor Red
    Write-Host "Put Qwen3-14B-Q4_K_M.gguf into backend\storage\models first." -ForegroundColor Yellow
    exit 1
}

Set-Location $ProjectRoot
Write-Host "Starting Qwen3 local server..." -ForegroundColor Green
Write-Host "Model: $ModelPath" -ForegroundColor Cyan
Write-Host "URL:   http://127.0.0.1:8081/v1" -ForegroundColor Cyan

llama-server -m $ModelPath --host 127.0.0.1 --port 8081 -c 8192 --jinja
