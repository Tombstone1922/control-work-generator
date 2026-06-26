$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$ModelsDir = Join-Path $ProjectRoot "backend\storage\models"

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

function Find-Qwen8Model {
    if (!(Test-Path $ModelsDir)) {
        return $null
    }

    $patterns = @(
        "Qwen3-8B-Q4_K_M.gguf",
        "*Qwen3*8B*Q4_K_M*.gguf",
        "*qwen3*8b*q4_k_m*.gguf",
        "*Qwen3-8B*.gguf"
    )

    foreach ($pattern in $patterns) {
        $found = Get-ChildItem -Path $ModelsDir -Filter $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }

    return $null
}

function Start-LlamaServerWithArgs($argsList, $label) {
    Write-Host "Trying llama-server launch: $label" -ForegroundColor Cyan
    & $LlamaServer @argsList
    if ($LASTEXITCODE -ne 0) {
        throw "llama-server failed with exit code $LASTEXITCODE"
    }
}

$ModelPath = Find-Qwen8Model
if (!$ModelPath) {
    Write-Host "Qwen3 8B GGUF model file not found in:" -ForegroundColor Red
    Write-Host "  $ModelsDir" -ForegroundColor Red
    Write-Host "Put Qwen3-8B-Q4_K_M.gguf into backend\storage\models first." -ForegroundColor Yellow
    exit 1
}

$LlamaServer = Find-LlamaServer
if (!$LlamaServer) {
    Write-Host "llama-server was not found." -ForegroundColor Red
    Write-Host "Install llama.cpp first, then restart PowerShell:" -ForegroundColor Yellow
    Write-Host "  winget install llama.cpp" -ForegroundColor Cyan
    exit 1
}

Set-Location $ProjectRoot
Write-Host "Starting Qwen3 8B fast local server..." -ForegroundColor Green
Write-Host "llama-server: $LlamaServer" -ForegroundColor Cyan
Write-Host "Model:        $ModelPath" -ForegroundColor Cyan
Write-Host "URL:          http://127.0.0.1:8083/v1" -ForegroundColor Cyan
Write-Host "Params:       -c 4096 -t 8 -ngl 99 -np 1 --flash-attn auto" -ForegroundColor Cyan

$baseArgs = @(
    "-m", $ModelPath,
    "--host", "127.0.0.1",
    "--port", "8083",
    "-c", "4096",
    "-t", "8",
    "-ngl", "99",
    "-np", "1"
)

try {
    Start-LlamaServerWithArgs ($baseArgs + @("--jinja", "--flash-attn", "auto")) "optimized + jinja + flash-attn auto"
} catch {
    Write-Host "Failed optimized flash-attn launch. Trying without flash-attn..." -ForegroundColor Yellow
    try {
        Start-LlamaServerWithArgs ($baseArgs + @("--jinja")) "optimized + jinja"
    } catch {
        Write-Host "Failed with --jinja. Trying basic optimized launch..." -ForegroundColor Yellow
        Start-LlamaServerWithArgs $baseArgs "optimized basic"
    }
}
