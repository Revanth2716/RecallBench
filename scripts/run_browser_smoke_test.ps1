# PowerShell orchestrator for running the browser smoke test with full teardown.
$ErrorActionPreference = "Stop"

$workspaceRoot = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $workspaceRoot

Write-Host "=== Starting RecallBench Browser Smoke Test Orchestrator ===" -ForegroundColor Cyan

# Function to test port availability with retry
function Wait-ForHttpOk ($url, $maxRetries = 20, $delaySec = 1) {
    for ($i = 1; $i -le $maxRetries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Host "Service at $url is ready!" -ForegroundColor Green
                return $true
            }
        } catch {
            Start-Sleep -Seconds $delaySec
        }
    }
    throw "Timeout waiting for $url to become available."
}

# Cleanup any orphaned processes on target ports
function Cleanup-Port ($port) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conns) {
        $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $pids) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
}

Cleanup-Port 8000
Cleanup-Port 5173
Cleanup-Port 9222

$backendProc = $null
$frontendProc = $null
$chromeProc = $null

try {
    # 1. Start Backend API server
    Write-Host "`n[1/3] Launching Backend API (FastAPI / Uvicorn on :8000)..." -ForegroundColor Yellow
    $backendProc = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory "$workspaceRoot\backend" `
        -PassThru

    Wait-ForHttpOk "http://127.0.0.1:8000/health" 15 1

    # 2. Start Frontend Dev server
    Write-Host "`n[2/3] Launching Frontend (Vite on :5173)..." -ForegroundColor Yellow
    $frontendProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173" `
        -WorkingDirectory "$workspaceRoot\frontend" `
        -PassThru

    Wait-ForHttpOk "http://127.0.0.1:5173" 20 1

    # 3. Launch Headless Google Chrome
    Write-Host "`n[3/3] Launching Google Chrome (Headless with CDP on :9222)..." -ForegroundColor Yellow
    $chromeProfile = "$env:TEMP\recallbench_chrome_smoke"
    if (Test-Path $chromeProfile) { Remove-Item -Recurse -Force $chromeProfile -ErrorAction SilentlyContinue }

    $chromeProc = Start-Process -FilePath "C:\Program Files\Google\Chrome\Application\chrome.exe" `
        -ArgumentList "--headless=new", "--remote-debugging-port=9222", "--user-data-dir=$chromeProfile", "--disable-gpu", "--no-first-run", "--no-default-browser-check" `
        -PassThru

    Wait-ForHttpOk "http://127.0.0.1:9222/json/version" 15 1

    # 4. Run the Node.js CDP smoke test
    Write-Host "`n[Automated Browser Navigation & Screenshot Capture] Running scripts/smoke_runner.cjs..." -ForegroundColor Cyan
    node scripts/smoke_runner.cjs
    $smokeExitCode = $LASTEXITCODE

    if ($smokeExitCode -eq 0) {
        Write-Host "`n[OK] Browser smoke tests passed successfully!" -ForegroundColor Green
    } else {
        Write-Host "`n[FAIL] Browser smoke tests failed with exit code $smokeExitCode." -ForegroundColor Red
    }

} finally {
    Write-Host "`nCleaning up background processes..." -ForegroundColor DarkGray
    if ($chromeProc -and -not $chromeProc.HasExited) {
        Stop-Process -Id $chromeProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProc -and -not $frontendProc.HasExited) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    Cleanup-Port 8000
    Cleanup-Port 5173
    Cleanup-Port 9222
    Write-Host "Teardown complete." -ForegroundColor DarkGray
}
