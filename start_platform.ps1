# ============================================================
# DM AI Operating System v1.4.0-production - Startup Script
# Phase 12.2: Robust Remote Deployment & E2E Validation
# ============================================================
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$deploymentDir = "$scriptDir\deployment"
if (-not (Test-Path $deploymentDir)) { New-Item -ItemType Directory -Path $deploymentDir | Out-Null }
$logFile = "$deploymentDir\deployment.log"

function Write-Log {
    param([string]$message, [string]$level="INFO", [string]$color="White")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timestamp] [$level] $message"
    try {
        Add-Content -Path $logFile -Value $logLine -Encoding utf8 -ErrorAction SilentlyContinue
    } catch {
        # Suppress log file locking conflicts
    }
    if ($color -ne "None") {
        Write-Host "[$level] $message" -ForegroundColor $color
    }
}

# Clear previous deployment.log header
Write-Log "==========================================================" "INFO" "Cyan"
Write-Log "Starting DM AI OS Remote Deployment Bootstrapper (Phase 12.2)" "INFO" "Cyan"
Write-Log "Working Directory: $scriptDir" "INFO" "DarkGray"

# 1. Cloudflared configuration sanitization (Check all potential config paths)
$cfConfigPaths = @(
    "$env:USERPROFILE\.cloudflared\config.yml",
    "$env:USERPROFILE\.cloudflared\config.yaml",
    "$env:APPDATA\cloudflared\config.yml",
    "$env:APPDATA\cloudflared\config.yaml",
    "$env:LOCALAPPDATA\cloudflared\config.yml",
    "$env:LOCALAPPDATA\cloudflared\config.yaml",
    "$scriptDir\config.yml",
    "$scriptDir\config.yaml",
    "$scriptDir\.cloudflared\config.yml",
    "$scriptDir\.cloudflared\config.yaml"
)

foreach ($cfPath in $cfConfigPaths) {
    if (Test-Path $cfPath) {
        $bakPath = "$cfPath.bak"
        Write-Log "Found existing cloudflared config at '$cfPath'. Renaming to '$bakPath' to prevent tunnel target override." "WARN" "Yellow"
        Rename-Item -Path $cfPath -NewName "$cfPath.bak" -Force -ErrorAction SilentlyContinue
    }
}

# 2. Activate Virtual Environment
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    & ".\.venv\Scripts\Activate.ps1"
    Write-Log "Virtual environment activated" "INFO" "DarkGray"
}
$pyCmd = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

# 3. Check Ollama
$ollamaStatus = "OFFLINE"
try {
    $ollamaRes = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
    if ($ollamaRes) { $ollamaStatus = "CONNECTED" }
} catch {
    Write-Log "Ollama is OFFLINE. Local models might fail." "WARN" "Yellow"
}
Write-Log "Ollama Status: $ollamaStatus" "INFO" "DarkGray"

# 4. Cleanup any orphan processes from previous runs
Write-Log "Cleaning up any orphan cloudflared / uvicorn processes..." "INFO" "DarkGray"
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$port8000 = netstat -ano | Select-String ":8000 " | Select-String "LISTENING"
if ($port8000) {
    $pid8000 = ($port8000 -split '\s+')[-1]
    Stop-Process -Id $pid8000 -Force -ErrorAction SilentlyContinue
    Write-Log "Killed process on port 8000 (PID $pid8000)" "INFO" "DarkGray"
}
$port8001 = netstat -ano | Select-String ":8001 " | Select-String "LISTENING"
if ($port8001) {
    $pid8001 = ($port8001 -split '\s+')[-1]
    Stop-Process -Id $pid8001 -Force -ErrorAction SilentlyContinue
    Write-Log "Killed process on port 8001 (PID $pid8001)" "INFO" "DarkGray"
}
Start-Sleep -Seconds 2

# 5. Launch API Gateway and MCP Server
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:scriptDir
    if (Test-Path ".\.venv\Scripts\python.exe") {
        & ".\.venv\Scripts\python.exe" -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --log-level info
    } else {
        python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --log-level info
    }
}
Write-Log "Started API Gateway on port 8000 (Job ID: $($apiJob.Id))" "INFO" "DarkGray"

$mcpJob = Start-Job -ScriptBlock {
    Set-Location $using:scriptDir
    if (Test-Path ".\.venv\Scripts\python.exe") {
        & ".\.venv\Scripts\python.exe" -m uvicorn src.mcp.mcp_server:mcp_app --host 0.0.0.0 --port 8001 --log-level info
    } else {
        python -m uvicorn src.mcp.mcp_server:mcp_app --host 0.0.0.0 --port 8001 --log-level info
    }
}
Write-Log "Started MCP Server on port 8001 (Job ID: $($mcpJob.Id))" "INFO" "DarkGray"

Start-Sleep -Seconds 4

# Local Health Check
try {
    $localHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 5 -ErrorAction SilentlyContinue
    if ($localHealth.status -eq "ONLINE") {
        Write-Log "Local API Gateway health check passed (HTTP 200)" "SUCCESS" "Green"
    } else {
        Write-Log "Local API Gateway health check failed." "ERROR" "Red"
    }
} catch {
    Write-Log "Local API Gateway not responding at http://127.0.0.1:8000" "ERROR" "Red"
}

# 6. Ensure Cloudflared binary exists
$CloudflaredUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
$CloudflaredPath = "$scriptDir\cloudflared.exe"

if (-not (Test-Path $CloudflaredPath)) {
    Write-Log "Downloading cloudflared.exe..." "INFO" "Cyan"
    Invoke-WebRequest -Uri $CloudflaredUrl -OutFile $CloudflaredPath
}

$targetUrl = "http://127.0.0.1:8000"
$tunnelArgs = "tunnel --url $targetUrl"
$curlExe = "curl.exe"
$curlTmp = "$deploymentDir\curl_tmp.txt"
$jsonPayloadFile = "$deploymentDir\ping_payload.json"
@{model="dm-autonomous-brain"; messages=@(@{role="user"; content="PING"})} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -Path $jsonPayloadFile

# Function to start cloudflared and validate end-to-end
function Start-And-Validate-Tunnel {
    $maxTunnelRetries = 5
    $tunnelAttempt = 0
    $e2eSuccess = $false
    $global:publicUrl = ""
    $global:tunnelProcess = $null

    while (-not $e2eSuccess -and $tunnelAttempt -lt $maxTunnelRetries) {
        $tunnelAttempt++
        Write-Log "Starting Cloudflare Quick Tunnel (Attempt $tunnelAttempt/$maxTunnelRetries): $CloudflaredPath $tunnelArgs" "INFO" "Cyan"

        # Cleanup existing cloudflared log
        $cfLogPath = "$scriptDir\cloudflared.log"
        if (Test-Path $cfLogPath) { Remove-Item $cfLogPath -Force -ErrorAction SilentlyContinue }

        $global:tunnelProcess = Start-Process -FilePath $CloudflaredPath -ArgumentList $tunnelArgs -NoNewWindow -PassThru -RedirectStandardError $cfLogPath

        # Parse log to get public URL
        $extractedUrl = ""
        $urlRetries = 0
        Write-Log "Waiting for public tunnel URL allocation..." "INFO" "Yellow"

        while ($extractedUrl -eq "" -and $urlRetries -lt 25) {
            Start-Sleep -Seconds 2
            if (Test-Path $cfLogPath) {
                $logContent = Get-Content $cfLogPath -Tail 30 -ErrorAction SilentlyContinue
                foreach ($line in $logContent) {
                    if ($line -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
                        $extractedUrl = $matches[0]
                        Write-Log "Allocated Public Tunnel URL: $extractedUrl" "SUCCESS" "Green"
                        break
                    }
                }
            }
            $urlRetries++
        }

        if (-not $extractedUrl) {
            Write-Log "Failed to extract public URL from cloudflared after 50 seconds. Restarting tunnel..." "WARN" "Yellow"
            if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
                Stop-Process -Id $global:tunnelProcess.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 3
            continue
        }

        $global:publicUrl = $extractedUrl

        # Poll /health until HTTP 200 or timeout
        Write-Log "Waiting for Cloudflare Edge propagation on $global:publicUrl/health..." "INFO" "Yellow"
        $healthCode = ""
        $healthRetry = 0
        $healthMaxRetries = 15

        while ($healthCode -ne "200" -and $healthRetry -lt $healthMaxRetries) {
            $healthRetry++
            Start-Sleep -Seconds 3
            $t0 = Get-Date
            $healthCode = & $curlExe -s -k -L -o $curlTmp -w "%{http_code}" --connect-timeout 10 "$global:publicUrl/health"
            $t1 = Get-Date
            $elapsedMs = [math]::Round(($t1 - $t0).TotalMilliseconds)
            $healthCode = $healthCode.Trim()

            Write-Log "[Check 1/4] GET /health attempt ${healthRetry}/${healthMaxRetries}: HTTP $healthCode (${elapsedMs}ms)" "INFO" "DarkGray"
        }

        if ($healthCode -ne "200") {
            Write-Log "Cloudflare Tunnel $global:publicUrl/health failed to return 200 (Got: '$healthCode'). Restarting cloudflared tunnel..." "WARN" "Yellow"
            if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
                Stop-Process -Id $global:tunnelProcess.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 3
            continue
        }

        Write-Log "[Check 1/4] Public GET /health PASSED (HTTP 200)" "SUCCESS" "Green"

        # Check 2: /docs
        Write-Log "[Check 2/4] Testing GET $global:publicUrl/docs ..." "INFO" "Yellow"
        $t0 = Get-Date
        $docsCode = & $curlExe -s -k -L -o $curlTmp -w "%{http_code}" --connect-timeout 10 "$global:publicUrl/docs"
        $t1 = Get-Date
        $docsCode = $docsCode.Trim()
        $docsMs = [math]::Round(($t1 - $t0).TotalMilliseconds)

        if ($docsCode -ne "200") {
            Write-Log "[Check 2/4] GET /docs FAILED (HTTP $docsCode). Retrying full tunnel allocation..." "WARN" "Yellow"
            if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
                Stop-Process -Id $global:tunnelProcess.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 3
            continue
        }
        Write-Log "[Check 2/4] Public GET /docs PASSED (HTTP 200, ${docsMs}ms)" "SUCCESS" "Green"

        # Check 3: /v1/models
        Write-Log "[Check 3/4] Testing GET $global:publicUrl/v1/models ..." "INFO" "Yellow"
        $t0 = Get-Date
        $modelsCode = & $curlExe -s -k -L -o $curlTmp -w "%{http_code}" --connect-timeout 10 -H "X-API-Key: dm-secret-key-v1" "$global:publicUrl/v1/models"
        $t1 = Get-Date
        $modelsCode = $modelsCode.Trim()
        $modelsMs = [math]::Round(($t1 - $t0).TotalMilliseconds)

        if ($modelsCode -ne "200") {
            Write-Log "[Check 3/4] GET /v1/models FAILED (HTTP $modelsCode). Retrying full tunnel allocation..." "WARN" "Yellow"
            if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
                Stop-Process -Id $global:tunnelProcess.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 3
            continue
        }
        $modelsBody = Get-Content $curlTmp -Raw 2>$null
        Write-Log "[Check 3/4] Public GET /v1/models PASSED (HTTP 200, ${modelsMs}ms)" "SUCCESS" "Green"
        Write-Log "  Models Response Snippet: $($modelsBody.Substring(0, [math]::Min(100, $modelsBody.Length)))" "INFO" "DarkGray"

        # Check 4: POST /v1/chat/completions
        Write-Log "[Check 4/4] Testing POST $global:publicUrl/v1/chat/completions ..." "INFO" "Yellow"
        $t0 = Get-Date
        $chatCode = & $curlExe -s -k -L -o $curlTmp -w "%{http_code}" --connect-timeout 15 --max-time 60 -X POST `
            -H "Content-Type: application/json" `
            -H "X-API-Key: dm-secret-key-v1" `
            --data-binary "@$jsonPayloadFile" `
            "$global:publicUrl/v1/chat/completions"
        $t1 = Get-Date
        $chatCode = $chatCode.Trim()
        $chatMs = [math]::Round(($t1 - $t0).TotalMilliseconds)

        if ($chatCode -ne "200") {
            Write-Log "[Check 4/4] POST /v1/chat/completions FAILED (HTTP $chatCode). Retrying full tunnel allocation..." "WARN" "Yellow"
            if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
                Stop-Process -Id $global:tunnelProcess.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 3
            continue
        }
        $chatBody = Get-Content $curlTmp -Raw 2>$null
        Write-Log "[Check 4/4] Public POST /v1/chat/completions PASSED (HTTP 200, ${chatMs}ms)" "SUCCESS" "Green"
        Write-Log "  Chat Response Excerpt: $($chatBody.Substring(0, [math]::Min(120, $chatBody.Length)))" "INFO" "DarkGray"

        $e2eSuccess = $true
    }

    return $e2eSuccess
}

# Run tunnel startup & validation
$validated = Start-And-Validate-Tunnel

if (-not $validated) {
    Write-Log "FATAL: Could not establish a fully functional Cloudflare Quick Tunnel after multiple attempts." "FATAL" "Red"
    Write-Log "DO NOT SHOW READY - Deployment Failed." "FATAL" "Red"
    exit 1
}

# 7. Generate QRs & OpenAI Connection Assets (ONLY generated after 100% successful validation)
Write-Log "Generating QR Codes and OpenAI deployment configuration..." "INFO" "Cyan"
& $pyCmd scripts\generate_deployment_assets.py --url $global:publicUrl | Out-Null
Write-Log "Deployment Assets successfully generated in $deploymentDir" "SUCCESS" "Green"

# Append cloudflared.log summary to deployment.log
if (Test-Path "$scriptDir\cloudflared.log") {
    $cfLogExcerpt = Get-Content "$scriptDir\cloudflared.log" -Raw 2>$null
    try { Add-Content -Path $logFile -Value "`n--- CLOUDFLARED LOG START ---`n$cfLogExcerpt`n--- CLOUDFLARED LOG END ---`n" -Encoding utf8 -ErrorAction SilentlyContinue } catch {}
}

# 8. Final Banner
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "     DM AI OS REMOTE DEPLOYMENT FULLY OPERATIONAL         " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Public Web URL:" -ForegroundColor White
Write-Host "  $global:publicUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "OpenAI Base Endpoint (for iPhone / Remote Clients):" -ForegroundColor White
Write-Host "  $global:publicUrl/v1" -ForegroundColor Cyan
Write-Host ""
Write-Host "API Key:" -ForegroundColor White
Write-Host "  dm-secret-key-v1" -ForegroundColor Yellow
Write-Host ""
Write-Host "Default Model:" -ForegroundColor White
Write-Host "  dm-autonomous-brain" -ForegroundColor Yellow
Write-Host ""
Write-Host "Generated Assets:" -ForegroundColor White
Write-Host "  - Web QR:   deployment\dm_ai_os_qr.png" -ForegroundColor DarkGray
Write-Host "  - Config QR: deployment\openai_config_qr.png" -ForegroundColor DarkGray
Write-Host "  - JSON Config: deployment\openai_connection.json" -ForegroundColor DarkGray
Write-Host "  - Audit Log: deployment\deployment.log" -ForegroundColor DarkGray
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   [Press Ctrl+C to stop all background services & tunnel]" -ForegroundColor Yellow
Write-Host ""

# Monitor loop with auto-restart for cloudflared
try {
    while ($true) {
        if ($global:tunnelProcess -and $global:tunnelProcess.HasExited) {
            Write-Log "Cloudflared process died unexpectedly. Initiating automatic recovery..." "WARN" "Red"
            $revalidated = Start-And-Validate-Tunnel
            if ($revalidated) {
                Write-Log "Tunnel recovered and re-validated at $global:publicUrl" "SUCCESS" "Green"
                & $pyCmd scripts\generate_deployment_assets.py --url $global:publicUrl | Out-Null
            }
        }
        Start-Sleep -Seconds 5
    }
} finally {
    Write-Log "Stopping DM AI OS Services..." "INFO" "DarkGray"
    Stop-Job -Job $apiJob -ErrorAction SilentlyContinue
    Stop-Job -Job $mcpJob -ErrorAction SilentlyContinue
    Remove-Job -Job $apiJob -ErrorAction SilentlyContinue
    Remove-Job -Job $mcpJob -ErrorAction SilentlyContinue
    if ($global:tunnelProcess -and -not $global:tunnelProcess.HasExited) {
        Stop-Process -Id $global:tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Log "DM AI OS Remote Deployment Shutdown Complete." "INFO" "DarkGray"
}
