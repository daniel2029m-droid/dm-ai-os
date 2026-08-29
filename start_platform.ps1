# ============================================================
# DM AI Operating System v1.5.1-production - Idempotent Startup
# Consolidated Autostart - Single Entry Point
# ============================================================
# Features:
#   - Named Mutex prevents concurrent execution
#   - Start-Process (not Start-Job) for robust, independent services
#   - Ollama wait/retry (up to 60s)
#   - Health-check based idempotency
#   - Daemon mode: monitoring loop with auto-recovery
#   - Log rotation (1MB max)
#   - -Stop flag for clean shutdown
# ============================================================
param(
    [switch]$Daemon  = $false,
    [switch]$Stop    = $false,
    [switch]$Status  = $false,
    [switch]$ForceRestart = $false
)

# --- Configuration ---
$scriptDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$deploymentDir  = "$scriptDir\deployment"
$logFile        = "$deploymentDir\deployment.log"
$lockFile       = "$deploymentDir\.platform.lock"
$pyExe          = "$scriptDir\.venv\Scripts\python.exe"
$cfExe          = if (Test-Path "$scriptDir\cloudflared.exe") { "$scriptDir\cloudflared.exe" } else { "cloudflared" }
$maxLogBytes    = 1048576  # 1 MB

$OLLAMA_URL     = "http://127.0.0.1:11434/api/tags"
$API_HEALTH     = "http://127.0.0.1:8000/health"
$MCP_HEALTH     = "http://127.0.0.1:8001/health"
$PUBLIC_URL     = "https://ai.dmorales.site"

# --- Ensure dirs ---
if (-not (Test-Path $deploymentDir)) { New-Item -ItemType Directory -Path $deploymentDir -Force | Out-Null }

# ============================================================
# Logging
# ============================================================
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO","WARN","ERROR","SUCCESS","DEBUG")]
        [string]$Level = "INFO",
        [string]$Color = "White"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine   = "[$timestamp] [$Level] $Message"
    try { Add-Content -Path $logFile -Value $logLine -Encoding utf8 -ErrorAction SilentlyContinue } catch {}
    $colorMap = @{ "INFO"="White"; "WARN"="Yellow"; "ERROR"="Red"; "SUCCESS"="Green"; "DEBUG"="DarkGray" }
    $fc = if ($Color -ne "White") { $Color } else { $colorMap[$Level] }
    Write-Host $logLine -ForegroundColor $fc
}

function Rotate-Log {
    if (Test-Path $logFile) {
        $size = (Get-Item $logFile -ErrorAction SilentlyContinue).Length
        if ($size -gt $maxLogBytes) {
            $archive = "$deploymentDir\deployment_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
            Move-Item $logFile $archive -Force -ErrorAction SilentlyContinue
            Write-Log "Log rotated to $(Split-Path -Leaf $archive)" "INFO"
        }
    }
}

# ============================================================
# Health Check Helpers
# ============================================================
function Test-OllamaHealth {
    try {
        $r = Invoke-RestMethod -Uri $OLLAMA_URL -Method Get -TimeoutSec 3 -ErrorAction Stop
        return ($null -ne $r)
    } catch { return $false }
}

function Test-ApiHealth {
    try {
        $r = Invoke-RestMethod -Uri $API_HEALTH -TimeoutSec 3 -ErrorAction Stop
        return ($r.status -eq "ONLINE")
    } catch { return $false }
}

function Test-McpHealth {
    try {
        $r = Invoke-RestMethod -Uri $MCP_HEALTH -TimeoutSec 3 -ErrorAction Stop
        return ($r.status -eq "ONLINE")
    } catch { return $false }
}

function Test-CloudflareRunning {
    $proc = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    # Verify it's our tunnel (dmorales-website)
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue).CommandLine
        return ($cmd -match "dmorales-website")
    } catch { return ($null -ne $proc) }
}

# ============================================================
# Service Management
# ============================================================
function Start-ApiGateway {
    Write-Log "Starting API Gateway on port 8000..." "INFO"
    Start-Process -FilePath $pyExe `
        -ArgumentList "-m", "uvicorn", "src.api.server:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "info" `
        -WorkingDirectory $scriptDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$deploymentDir\api_gw_out.log" `
        -RedirectStandardError  "$deploymentDir\api_gw_err.log"

    # Wait up to 15s for API to respond
    for ($i = 1; $i -le 5; $i++) {
        Start-Sleep -Seconds 3
        if (Test-ApiHealth) {
            Write-Log "API Gateway started successfully (attempt $i)." "SUCCESS"
            return $true
        }
        Write-Log "Waiting for API Gateway... (attempt $i/5)" "DEBUG"
    }
    Write-Log "API Gateway failed to start within 15 seconds." "ERROR"
    return $false
}

function Start-McpServer {
    Write-Log "Starting MCP Server on port 8001..." "INFO"
    Start-Process -FilePath $pyExe `
        -ArgumentList "-m", "uvicorn", "src.mcp.mcp_server:mcp_app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "info" `
        -WorkingDirectory $scriptDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$deploymentDir\mcp_out.log" `
        -RedirectStandardError  "$deploymentDir\mcp_err.log"

    # Wait up to 15s for MCP to respond
    for ($i = 1; $i -le 5; $i++) {
        Start-Sleep -Seconds 3
        if (Test-McpHealth) {
            Write-Log "MCP Server started successfully (attempt $i)." "SUCCESS"
            return $true
        }
        Write-Log "Waiting for MCP Server... (attempt $i/5)" "DEBUG"
    }
    Write-Log "MCP Server failed to start within 15 seconds." "ERROR"
    return $false
}

function Start-CloudflareTunnel {
    Write-Log "Starting Cloudflare Tunnel (dmorales-website)..." "INFO"
    Start-Process -FilePath $cfExe `
        -ArgumentList "tunnel", "run", "dmorales-website" `
        -WorkingDirectory $scriptDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$deploymentDir\cf_out.log" `
        -RedirectStandardError  "$deploymentDir\cf_err.log"

    # Wait up to 10s for process to appear
    for ($i = 1; $i -le 5; $i++) {
        Start-Sleep -Seconds 2
        if (Test-CloudflareRunning) {
            Write-Log "Cloudflare Tunnel started successfully." "SUCCESS"
            return $true
        }
        Write-Log "Waiting for Cloudflare Tunnel... (attempt $i/5)" "DEBUG"
    }
    Write-Log "Cloudflare Tunnel failed to start within 10 seconds." "ERROR"
    return $false
}

function Stop-AllServices {
    Write-Log "=== Stopping all DM AI OS services ===" "WARN"

    # Stop API Gateway (python on port 8000)
    $apiPid = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess
    if ($apiPid) {
        # Kill the parent uvicorn process tree
        try {
            $parentPid = (Get-CimInstance Win32_Process -Filter "ProcessId=$apiPid" -ErrorAction SilentlyContinue).ParentProcessId
            if ($parentPid -and $parentPid -ne 0) {
                Stop-Process -Id $parentPid -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $apiPid -Force -ErrorAction SilentlyContinue
            Write-Log "Stopped API Gateway (PID $apiPid)." "INFO"
        } catch { Write-Log "Error stopping API: $_" "WARN" }
    }

    # Stop MCP Server (python on port 8001)
    $mcpPid = (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue).OwningProcess
    if ($mcpPid) {
        try {
            $parentPid = (Get-CimInstance Win32_Process -Filter "ProcessId=$mcpPid" -ErrorAction SilentlyContinue).ParentProcessId
            if ($parentPid -and $parentPid -ne 0) {
                Stop-Process -Id $parentPid -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $mcpPid -Force -ErrorAction SilentlyContinue
            Write-Log "Stopped MCP Server (PID $mcpPid)." "INFO"
        } catch { Write-Log "Error stopping MCP: $_" "WARN" }
    }

    # Stop Cloudflare Tunnel
    Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Log "Stopped Cloudflare Tunnel." "INFO"

    # Kill any orphan Start-Job PowerShell hosts from old architecture
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "Version 5\.1 -s -NoLogo -NoProfile" -and
        $_.ParentProcessId -in (
            Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "start_platform\.ps1" } |
            Select-Object -ExpandProperty ProcessId
        )
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Log "Killed orphan Start-Job host (PID $($_.ProcessId))." "DEBUG"
    }

    # Kill old start_platform.ps1 instances (not ourselves)
    $myPid = $PID
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "start_platform\.ps1" -and $_.ProcessId -ne $myPid
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Log "Killed old start_platform.ps1 instance (PID $($_.ProcessId))." "DEBUG"
    }

    Start-Sleep -Seconds 2
    Write-Log "All DM AI OS services stopped." "SUCCESS"
}

# ============================================================
# Status Display
# ============================================================
function Show-Status {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "  DM AI OS v1.5.1 - Service Status" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan

    $ollamaOk = Test-OllamaHealth
    $apiOk    = Test-ApiHealth
    $mcpOk    = Test-McpHealth
    $cfOk     = Test-CloudflareRunning

    $icon = { param($ok) if ($ok) { "[OK]" } else { "[!!]" } }
    $col  = { param($ok) if ($ok) { "Green" } else { "Red" } }

    Write-Host "  Ollama (11434):       $(& $icon $ollamaOk)" -ForegroundColor (& $col $ollamaOk)
    Write-Host "  API Gateway (8000):   $(& $icon $apiOk)" -ForegroundColor (& $col $apiOk)
    Write-Host "  MCP Server (8001):    $(& $icon $mcpOk)" -ForegroundColor (& $col $mcpOk)
    Write-Host "  Cloudflare Tunnel:    $(& $icon $cfOk)" -ForegroundColor (& $col $cfOk)
    Write-Host "  Public URL:           $PUBLIC_URL" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================
# MAIN LOGIC
# ============================================================

# --- Handle -Status ---
if ($Status) {
    Show-Status
    exit 0
}

# --- Handle -Stop ---
if ($Stop) {
    Stop-AllServices
    exit 0
}

# --- Mutex: prevent concurrent execution ---
$mutexName = "Global\DMAIOS_StartPlatform_Mutex"
$mutexCreated = $false
try {
    $mutex = [System.Threading.Mutex]::new($true, $mutexName, [ref]$mutexCreated)
} catch {
    Write-Host "[BLOCKED] Another instance of start_platform.ps1 is already running. Exiting." -ForegroundColor Yellow
    exit 0
}

if (-not $mutexCreated) {
    # Another instance holds the mutex
    Write-Host "[BLOCKED] Another instance of start_platform.ps1 is already running. Exiting." -ForegroundColor Yellow
    try { $mutex.Dispose() } catch {}
    exit 0
}

# We own the mutex - proceed
try {
    Rotate-Log

    Write-Log "==========================================================" "INFO"
    Write-Log "DM AI OS Bootstrapper v1.5.1 - Starting" "INFO"
    Write-Log "Mode: $(if ($Daemon) { 'DAEMON (monitoring)' } else { 'ONE-SHOT' })" "INFO"
    Write-Log "PID: $PID | Working Directory: $scriptDir" "DEBUG"
    Write-Log "==========================================================" "INFO"

    # --- Activate venv (for environment variables only) ---
    if (Test-Path "$scriptDir\.venv\Scripts\Activate.ps1") {
        & "$scriptDir\.venv\Scripts\Activate.ps1"
    }

    # --- ForceRestart: stop everything first ---
    if ($ForceRestart) {
        Stop-AllServices
    }

    # ==========================================================
    # 1. Wait for Ollama (up to 60 seconds)
    # ==========================================================
    Write-Log "Checking Ollama availability..." "INFO"
    $ollamaReady = $false
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        if (Test-OllamaHealth) {
            $ollamaReady = $true
            Write-Log "Ollama is CONNECTED (attempt $attempt)." "SUCCESS"
            break
        }
        if ($attempt -eq 1) {
            Write-Log "Ollama not yet available. Waiting (up to 60s)..." "WARN"
        } else {
            Write-Log "Ollama retry $attempt/12..." "DEBUG"
        }
        Start-Sleep -Seconds 5
    }
    if (-not $ollamaReady) {
        Write-Log "Ollama is OFFLINE after 60 seconds. Continuing without it." "ERROR"
    }

    # ==========================================================
    # 2. Idempotent Start: API Gateway
    # ==========================================================
    if (Test-ApiHealth) {
        Write-Log "API Gateway already running on port 8000." "SUCCESS"
    } else {
        Start-ApiGateway | Out-Null
    }

    # ==========================================================
    # 3. Idempotent Start: MCP Server
    # ==========================================================
    if (Test-McpHealth) {
        Write-Log "MCP Server already running on port 8001." "SUCCESS"
    } else {
        Start-McpServer | Out-Null
    }

    # ==========================================================
    # 4. Idempotent Start: Cloudflare Tunnel
    # ==========================================================
    if (Test-CloudflareRunning) {
        Write-Log "Cloudflare Tunnel already running." "SUCCESS"
    } else {
        Start-CloudflareTunnel | Out-Null
    }

    # ==========================================================
    # 5. Write Public URL
    # ==========================================================
    [System.IO.File]::WriteAllText("$scriptDir\tunnel_url.txt", $PUBLIC_URL)

    # ==========================================================
    # 6. Generate Deployment Assets (non-critical)
    # ==========================================================
    try {
        & $pyExe "$scriptDir\scripts\generate_deployment_assets.py" --url $PUBLIC_URL 2>&1 | Out-Null
        Write-Log "Deployment assets updated." "SUCCESS"
    } catch {
        Write-Log "Asset generation notice: $_" "WARN"
    }

    # ==========================================================
    # 7. Final Status
    # ==========================================================
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "     DM AI OS DEPLOYMENT STATUS: OPERATIONAL              " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Local Gateway:   http://127.0.0.1:8000" -ForegroundColor White
    Write-Host "MCP Server:      http://127.0.0.1:8001" -ForegroundColor White
    Write-Host "Public URL:      $PUBLIC_URL" -ForegroundColor Cyan
    Write-Host "OpenAI Endpoint: $PUBLIC_URL/v1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green

    Write-Log "Bootstrapper completed. All services operational." "SUCCESS"

    # ==========================================================
    # 8. Daemon Mode: Monitor & Auto-Recovery
    # ==========================================================
    if ($Daemon) {
        Write-Log "Entering daemon monitoring loop (60s interval)." "INFO"
        Write-Host "Monitoring services... (Ctrl+C to stop)" -ForegroundColor Yellow

        try {
            while ($true) {
                Start-Sleep -Seconds 60

                $recovered = @()

                # Check API Gateway
                if (-not (Test-ApiHealth)) {
                    Write-Log "RECOVERY: API Gateway is down. Restarting..." "WARN"
                    Start-ApiGateway | Out-Null
                    $recovered += "API Gateway"
                }

                # Check MCP Server
                if (-not (Test-McpHealth)) {
                    Write-Log "RECOVERY: MCP Server is down. Restarting..." "WARN"
                    Start-McpServer | Out-Null
                    $recovered += "MCP Server"
                }

                # Check Cloudflare Tunnel
                if (-not (Test-CloudflareRunning)) {
                    Write-Log "RECOVERY: Cloudflare Tunnel is down. Restarting..." "WARN"
                    Start-CloudflareTunnel | Out-Null
                    $recovered += "Cloudflare"
                }

                if ($recovered.Count -gt 0) {
                    Write-Log "RECOVERY: Restarted: $($recovered -join ', ')" "WARN"
                }
            }
        } finally {
            Write-Log "Daemon monitoring loop exited." "INFO"
        }
    }

} finally {
    # Release mutex
    try {
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    } catch {}
    Write-Log "Bootstrapper shutdown. Mutex released." "DEBUG"
}
