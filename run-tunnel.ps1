# Start the AI service (uvicorn :8000) and expose it through ngrok.
#
#   .\run-tunnel.ps1                  start both, verify /ready through the tunnel
#   .\run-tunnel.ps1 -Stop            stop both
#   .\run-tunnel.ps1 -UpdateBackend   ALSO rewrite jobfit-backend\.env to the public URL
#
# Leave -UpdateBackend OFF while the backend runs on this same machine. It should stay on
# AI_SERVICE_URL=http://127.0.0.1:8000/api/v1 -- sending a local backend out through the
# tunnel and back adds a failure point, and when ngrok dies resume parsing breaks with
# "We couldn't read this resume." (127.0.0.1, not localhost: localhost resolves to ::1
# first on Windows, where another container has been known to answer on :8000.)
#
# Ollama must already be running (it is a Windows service; check with `ollama list`).

# -Domain: the account's reserved ngrok domain (e.g. yourname.ngrok-free.app). WITHOUT
# it ngrok hands out a NEW random hostname on every start, which is fine for local use
# and useless for anything that has to be told the address in advance - the deployed
# backend on Cloud Run reads AI_SERVICE_URL from its build config and cannot follow a
# hostname that changes. With it, the tunnel comes up at the same address every time, so
# the deployed AI_SERVICE_URL stays correct across laptop restarts. Defaults to the
# reserved domain set as the default below; pass -Domain "" for the old random behaviour.
param([switch]$Stop, [switch]$UpdateBackend, [string]$Domain = "stellar-nanny-thermos.ngrok-free.dev")

$ErrorActionPreference = "Stop"
$Root       = $PSScriptRoot
$Python     = Join-Path $Root ".venv\Scripts\python.exe"
$BackendEnv = Join-Path (Split-Path $Root -Parent) "jobfit-backend\.env"
$Port       = 8000
$LogDir     = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory $LogDir | Out-Null }

function Get-PortOwner($p) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.OwningProcess } else { return $null }
}

if ($Stop) {
    $owner = Get-PortOwner $Port
    if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue; Write-Host "stopped service on port $Port" }
    Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Tunnel and service stopped."
    exit 0
}

# 1. FastAPI service
if (Get-PortOwner $Port) {
    Write-Host "[1/4] service already listening on :$Port"
} else {
    Write-Host "[1/4] starting uvicorn on :$Port"
    # Hidden + redirected, NOT a minimized console window: a console child dies when the
    # terminal that spawned it closes or gets Ctrl+C, which is how the service kept
    # vanishing and every parse then failed with "fetch failed".
    Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","app.main:app","--port","$Port" `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "uvicorn.out.log") `
        -RedirectStandardError  (Join-Path $LogDir "uvicorn.log")
}

# 2. ngrok tunnel (4040 is its local inspector; if it is gone, ngrok is not running)
if (Get-PortOwner 4040) {
    Write-Host "[2/4] ngrok already running"
} else {
    $ngrokArgs = @("http", "$Port", "--log=stdout", "--log-level=info")
    if ($Domain) {
        $ngrokArgs += "--url=$Domain"
        Write-Host "[2/4] starting ngrok on fixed domain $Domain"
    } else {
        Write-Host "[2/4] starting ngrok (random hostname - pass -Domain for a fixed one)"
    }
    Start-Process -FilePath "ngrok" -ArgumentList $ngrokArgs `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "ngrok.log") `
        -RedirectStandardError  (Join-Path $LogDir "ngrok.err.log")
}

# 3. wait for the public URL
$url = $null
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    try {
        $t = (Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels").tunnels | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1
        if ($t) { $url = $t.public_url }
    } catch {}
}
if (-not $url) { throw "ngrok did not report a public URL within 30s. Check the authtoken: ngrok config check" }
Write-Host "[3/4] public URL: $url"

# 4. verify /ready THROUGH the tunnel. The skip header avoids ngrok's free-tier
#    browser warning page, which replaces the JSON body for browser-like clients.
$ready = $null
for ($i = 0; $i -lt 30 -and -not $ready; $i++) {
    try { $ready = Invoke-RestMethod "$url/api/v1/ready" -Headers @{ "ngrok-skip-browser-warning" = "1" } } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw "service did not answer /ready through the tunnel." }
if ($ready.status -ne "ready") {
    Write-Host "[4/4] NOT READY: $($ready.reason) - $($ready.detail)" -ForegroundColor Red
} else {
    Write-Host "[4/4] /ready OK  (generation=$($ready.models.generation), embedding=$($ready.models.embedding))" -ForegroundColor Green
}

# 5. the backend's AI_SERVICE_URL must include the /api/v1 prefix, tunnel or not.
$target = "$url/api/v1"
$current = "?"
if (Test-Path $BackendEnv) {
    $text = [System.IO.File]::ReadAllText($BackendEnv)
    $current = ([regex]::Match($text, "(?m)^AI_SERVICE_URL=(.*)$")).Groups[1].Value
}

if (-not $UpdateBackend) {
    Write-Host "backend .env left as-is: AI_SERVICE_URL=$current"
    Write-Host "  (-UpdateBackend points it at $target - only if the backend runs elsewhere)"
} elseif (-not (Test-Path $BackendEnv)) {
    Write-Host "backend .env not found at $BackendEnv - set AI_SERVICE_URL=$target yourself" -ForegroundColor Yellow
} elseif ($text -notmatch "(?m)^AI_SERVICE_URL=.*$") {
    Write-Host "backend .env has no AI_SERVICE_URL line - add: AI_SERVICE_URL=$target" -ForegroundColor Yellow
} elseif ($current -eq $target) {
    Write-Host "backend .env already has AI_SERVICE_URL=$target"
} else {
    $new = [regex]::Replace($text, "(?m)^AI_SERVICE_URL=.*$", "AI_SERVICE_URL=$target")
    [System.IO.File]::WriteAllText($BackendEnv, $new, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "backend .env updated: AI_SERVICE_URL=$target  (restart the backend to pick it up)"
}

Write-Host ""
Write-Host "AI service is live at $url"
Write-Host "Traffic inspector:    http://127.0.0.1:4040"
Write-Host "Logs:                 $LogDir  (uvicorn.log, ngrok.log)"
Write-Host "Stop with:            .\run-tunnel.ps1 -Stop"
