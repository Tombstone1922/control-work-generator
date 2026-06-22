$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$BackendDir = Join-Path $ProjectRoot "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvActivate = Join-Path $VenvDir "Scripts\Activate.ps1"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (!(Test-Path $BackendDir)) {
    Write-Host "Backend folder not found: $BackendDir" -ForegroundColor Red
    exit 1
}

Set-Location $BackendDir

$shouldRecreateVenv = $false
if (!(Test-Path $VenvActivate) -or !(Test-Path $VenvPython)) {
    $shouldRecreateVenv = $true
} else {
    $realPrefix = & $VenvPython -c "import sys; print(sys.prefix)"
    if ($realPrefix -notlike "$BackendDir*") {
        Write-Host "Existing .venv points to another path:" -ForegroundColor Yellow
        Write-Host "  $realPrefix" -ForegroundColor Yellow
        Write-Host "Expected path under:" -ForegroundColor Yellow
        Write-Host "  $BackendDir" -ForegroundColor Yellow
        $shouldRecreateVenv = $true
    }
}

if ($shouldRecreateVenv) {
    if (Test-Path $VenvDir) {
        Write-Host "Removing copied/stale .venv..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }
    Write-Host "Creating fresh .venv in $BackendDir..." -ForegroundColor Green
    python -m venv .venv
}

. $VenvActivate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
