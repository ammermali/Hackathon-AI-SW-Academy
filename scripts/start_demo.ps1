param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendDir = Join-Path $RootDir "frontend"
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $RootDir "storage\logs"

$BackendUrl = "http://127.0.0.1:8000"
$HealthUrl = "$BackendUrl/health"
$FrontendUrl = "http://127.0.0.1:5173"

$BackendProc = $null
$FrontendProc = $null

function Test-TcpPortOpen {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port,
        [int]$TimeoutMs = 250
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [System.Diagnostics.Process]$Process,
        [string]$ServiceName,
        [string]$ErrLogPath,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($null -ne $Process -and $Process.HasExited) {
            Write-Host ""
            Write-Host "[ERRORE] $ServiceName terminato prematuramente (exit code $($Process.ExitCode))." -ForegroundColor Red
            if (Test-Path $ErrLogPath) {
                Write-Host "--- Ultime righe log ($ErrLogPath) ---" -ForegroundColor DarkGray
                Get-Content $ErrLogPath -Tail 20
            }
            throw "$ServiceName non avviato."
        }
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 600
        }
    }
    throw "Timeout attesa avvio $ServiceName ($Url)."
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process, [string]$Label)
    if ($null -eq $Process) { return }
    try {
        if (-not $Process.HasExited) {
            Write-Host "Arresto $Label (PID $($Process.Id))..." -ForegroundColor DarkYellow
            & taskkill.exe /PID $Process.Id /T /F *> $null
        }
    }
    catch {
        # Best effort cleanup
    }
}

try {
    if (-not [Console]::IsOutputRedirected) {
        try { Clear-Host } catch {}
    }
    Write-Host "=====================================================" -ForegroundColor Cyan
    Write-Host "  AI Software Academy - Avvio Demo Integrato" -ForegroundColor Cyan
    Write-Host "=====================================================" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Path $VenvPython)) {
        throw "Ambiente Python non trovato in '$VenvPython'. Crea prima il virtualenv (.venv) e installa le dipendenze."
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js / npm non trovati nel PATH di sistema."
    }

    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "[0/3] Installazione dipendenze frontend (npm install)..." -ForegroundColor Yellow
        Push-Location $FrontendDir
        try {
            & npm install
            if ($LASTEXITCODE -ne 0) {
                throw "npm install fallito."
            }
        }
        finally {
            Pop-Location
        }
    }

    $env:PYTHONPATH = Join-Path $RootDir "src"
    Write-Host "[1/3] Verifica profili demo nel database..." -ForegroundColor Cyan
    & $VenvPython (Join-Path $RootDir "scripts\seed_demo_users.py") | Out-Null

    $BackendOutLog = Join-Path $LogDir "demo-backend.log"
    $BackendErrLog = Join-Path $LogDir "demo-backend.err.log"
    $FrontendOutLog = Join-Path $LogDir "demo-frontend.log"
    $FrontendErrLog = Join-Path $LogDir "demo-frontend.err.log"

    if (Test-TcpPortOpen -Port 8000) {
        Write-Host "[1/3] Backend gia attivo su $BackendUrl (riutilizzo istanza esistente)." -ForegroundColor Green
    }
    else {
        Write-Host "[1/3] Avvio Backend FastAPI + RAG su $BackendUrl ..." -ForegroundColor Cyan
        $BackendProc = Start-Process -FilePath $VenvPython `
            -ArgumentList @("-m", "uvicorn", "operator_copilot.api.main:app", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $RootDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $BackendOutLog `
            -RedirectStandardError $BackendErrLog `
            -PassThru
        Wait-HttpReady -Url $HealthUrl -Process $BackendProc -ServiceName "Backend FastAPI" -ErrLogPath $BackendErrLog -TimeoutSeconds 90
        Write-Host "      Backend pronto ($HealthUrl)." -ForegroundColor Green
    }

    if (Test-TcpPortOpen -Port 5173) {
        Write-Host "[2/3] Frontend Vite gia attivo su $FrontendUrl (riutilizzo istanza esistente)." -ForegroundColor Green
    }
    else {
        Write-Host "[2/3] Avvio Frontend React + Vite su $FrontendUrl ..." -ForegroundColor Cyan
        $FrontendProc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList @("/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
            -WorkingDirectory $FrontendDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $FrontendOutLog `
            -RedirectStandardError $FrontendErrLog `
            -PassThru
        Wait-HttpReady -Url $FrontendUrl -Process $FrontendProc -ServiceName "Frontend Vite" -ErrLogPath $FrontendErrLog -TimeoutSeconds 45
        Write-Host "      Frontend pronto ($FrontendUrl)." -ForegroundColor Green
    }

    if (-not $NoBrowser) {
        Write-Host "[3/3] Apertura browser su $FrontendUrl ..." -ForegroundColor Cyan
        Start-Process $FrontendUrl | Out-Null
    }
    else {
        Write-Host "[3/3] Modalita -NoBrowser attiva: browser non aperto automaticamente." -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "Demo attiva in questa unica finestra:" -ForegroundColor Green
    Write-Host "  - Web App UI : $FrontendUrl"
    Write-Host "  - API Docs   : $BackendUrl/docs"
    Write-Host "  - Log files  : $LogDir"
    Write-Host ""

    if ([Console]::IsInputRedirected) {
        Read-Host "Premi Invio per arrestare la demo" | Out-Null
    }
    else {
        Write-Host "Premi [Q], [ESC] oppure [CTRL+C] per arrestare i server e chiudere." -ForegroundColor Yellow
        while ($true) {
            if ($null -ne $BackendProc -and $BackendProc.HasExited) {
                throw "Il processo Backend si e arrestato inattesamente (exit code $($BackendProc.ExitCode)). Vedi $BackendErrLog."
            }
            if ($null -ne $FrontendProc -and $FrontendProc.HasExited) {
                throw "Il processo Frontend si e arrestato inattesamente (exit code $($FrontendProc.ExitCode)). Vedi $FrontendErrLog."
            }
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq [ConsoleKey]::Q -or $key.Key -eq [ConsoleKey]::Escape) {
                    break
                }
            }
            Start-Sleep -Milliseconds 300
        }
    }
}
finally {
    Write-Host ""
    Stop-ProcessTree -Process $FrontendProc -Label "Frontend Vite"
    Stop-ProcessTree -Process $BackendProc -Label "Backend FastAPI"
    Write-Host "Demo arrestata." -ForegroundColor Cyan
}
