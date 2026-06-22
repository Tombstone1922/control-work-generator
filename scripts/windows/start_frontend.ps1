$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\control-work-generator"
$FrontendDir = Join-Path $ProjectRoot "frontend"

if (!(Test-Path $FrontendDir)) {
    Write-Host "Frontend folder not found: $FrontendDir" -ForegroundColor Red
    exit 1
}

Set-Location $FrontendDir

if (!(Test-Path "node_modules")) {
    Write-Host "node_modules not found. Running npm install..." -ForegroundColor Yellow
    npm install
}

npm run dev
