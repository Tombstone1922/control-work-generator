$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$ModelPath = Join-Path $ProjectRoot "backend\storage\models\Qwen3-14B-Q4_K_M.gguf"

function Find-LlamaServer {
    $command = Get-Command llama-server -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $ProjectRoot "tools\llama.cpp\llama-server.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\*\llama-server.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\llama.cpp\llama-server.exe"),
        (Join-Path $env:ProgramFiles "llama.cpp\llama-server.exe")
    )

    foreach ($candidate in $candidates) {
        $found = Get-ChildItem -Path $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }

    return $null
}

if (!(Test-Path $ModelPath)) {
    Write-Host "Model file not found:" -ForegroundColor Red
    Write-Host "  $ModelPath" -ForegroundColor Red
    Write-Host "Put Qwen3-14B-Q4_K_M.gguf into backend\storage\models first." -ForegroundColor Yellow
    exit 1
}

$LlamaServer = Find-LlamaServer
if (!$LlamaServer) {
    Write-Host "llama-server was not found." -ForegroundColor Red
    Write-Host "Install llama.cpp first, then restart PowerShell:" -ForegroundColor Yellow
    Write-Host "  winget install llama.cpp" -ForegroundColor Cyan
    Write-Host "If winget cannot find it, run:" -ForegroundColor Yellow
    Write-Host "  winget search llama" -ForegroundColor Cyan
    Write-Host "Then install the package that contains llama.cpp / llama-server." -ForegroundColor Yellow
    exit 1
}

Set-Location $ProjectRoot
Write-Host "Starting Qwen3 local server optimized for RTX 5070..." -ForegroundColor Green
Write-Host "llama-server: $LlamaServer" -ForegroundColor Cyan
Write-Host "Model:        $ModelPath" -ForegroundColor Cyan
Write-Host "URL:          http://127.0.0.1:8081/v1" -ForegroundColor Cyan
Write-Host "Params:       -c 4096 -t 8 -ngl 99 -np 1" -ForegroundColor Cyan

$baseArgs = @(
    "-m", $ModelPath,
    "--host", "127.0.0.1",
    "--port", "8081",
    "-c", "4096",
    "-t", "8",
    "-ngl", "99",
    "-np", "1"
)

try {
    & $LlamaServer @baseArgs --jinja -fa
} catch {
    Write-Host "Failed to start with --jinja -fa. Trying without -fa..." -ForegroundColor Yellow
    try {
        & $LlamaServer @baseArgs --jinja
    } catch {
        Write-Host "Failed to start with --jinja. Trying basic optimized launch..." -ForegroundColor Yellow
        & $LlamaServer @baseArgs
    }
}
