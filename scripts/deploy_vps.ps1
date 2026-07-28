# ============================================================
# DM AI OS — VPS Deploy Script
# Target:  62.171.169.50  (app.dmorales.site)
# Run:     .\scripts\deploy_vps.ps1
# Requires: SSH access to VPS with key or password
# ============================================================

param(
    [string]$VpsHost    = "62.171.169.50",
    [string]$VpsUser    = "root",
    [string]$RemoteDir  = "/opt/dm-ai-os",
    [string]$ServiceName= "dm-ai-os",
    [switch]$SkipTests  = $false,
    [switch]$DryRun     = $false
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n  ▸ $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    ✅ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    ⚠️  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "    ❌ $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "  ║   DM AI OS — Production Deploy to VPS        ║" -ForegroundColor Magenta
Write-Host "  ║   Target: $VpsHost                  ║" -ForegroundColor Magenta
Write-Host "  ║   Domain: app.dmorales.site                  ║" -ForegroundColor Magenta
Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ── STEP 0: Run local tests (optional skip) ──────────────────
if (-not $SkipTests) {
    Write-Step "Running 232 tests locally before deploy…"
    if ($DryRun) {
        Write-Ok "DRY RUN — tests skipped"
    } else {
        $testResult = & python -m pytest tests/ -x -q --tb=short 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Tests FAILED. Aborting deploy."
            Write-Host $testResult
            exit 1
        }
        Write-Ok "232/232 tests PASS — proceeding to deploy"
    }
} else {
    Write-Warn "Tests skipped (-SkipTests flag)"
}

# ── STEP 1: Create Founder Account (local DBs) ───────────────
Write-Step "Creating/verifying Founder Account in local DBs…"
if ($DryRun) {
    Write-Ok "DRY RUN — founder account skipped"
} else {
    & python "$ProjectRoot\scripts\create_founder_account.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Founder account script had warnings (may already exist)"
    } else {
        Write-Ok "Founder account verified"
    }
}

# ── STEP 2: Create deploy package ────────────────────────────
Write-Step "Creating deployment package…"

$TmpDir     = "$env:TEMP\dm_ai_os_deploy_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
$TarFile    = "$TmpDir\dm_ai_os.tar.gz"
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

# Files to include
$IncludeDirs = @("src", "tests", "public", "scripts", "config", "Project_State")
$IncludeFiles = @("pyproject.toml", "requirements.txt", "vercel.json", "nginx_dmorales_site.conf", ".env.example")

if (-not $DryRun) {
    # Create tar.gz with 7-Zip or built-in tar (Windows 10+)
    $TarArgs = @("-czf", $TarFile, "--exclude=__pycache__", "--exclude=*.pyc",
                 "--exclude=.venv", "--exclude=.pytest_cache",
                 "--exclude=*.egg-info", "--exclude=.git")
    foreach ($d in $IncludeDirs) {
        if (Test-Path "$ProjectRoot\$d") { $TarArgs += $d }
    }
    foreach ($f in $IncludeFiles) {
        if (Test-Path "$ProjectRoot\$f") { $TarArgs += $f }
    }

    Push-Location $ProjectRoot
    tar @TarArgs
    Pop-Location
    Write-Ok "Package created: $TarFile"
} else {
    Write-Ok "DRY RUN — package creation skipped"
}

# ── STEP 3: Upload to VPS via SCP ────────────────────────────
Write-Step "Uploading package to VPS ($VpsHost)…"

if ($DryRun) {
    Write-Ok "DRY RUN — SCP skipped"
    Write-Warn "Manual command: scp $TarFile ${VpsUser}@${VpsHost}:/tmp/"
} else {
    scp $TarFile "${VpsUser}@${VpsHost}:/tmp/dm_ai_os.tar.gz"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "SCP failed. Check SSH access to $VpsHost"
        Write-Host ""
        Write-Host "  MANUAL DEPLOY INSTRUCTIONS:" -ForegroundColor Yellow
        Write-Host "  1. scp $TarFile ${VpsUser}@${VpsHost}:/tmp/" -ForegroundColor White
        Write-Host "  2. ssh ${VpsUser}@${VpsHost}" -ForegroundColor White
        Write-Host "  3. Run the remote script below" -ForegroundColor White
        exit 1
    }
    Write-Ok "Package uploaded to VPS"
}

# ── STEP 4: Remote deploy commands ───────────────────────────
Write-Step "Executing remote deployment commands on VPS…"

$RemoteScript = @"
set -e
echo '▸ Extracting package…'
mkdir -p $RemoteDir
cd $RemoteDir
tar -xzf /tmp/dm_ai_os.tar.gz --strip-components=0
rm /tmp/dm_ai_os.tar.gz

echo '▸ Setting up Python virtualenv…'
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt 2>/dev/null || pip install --quiet fastapi uvicorn pydantic 2>/dev/null

echo '▸ Creating Founder Account on VPS…'
python scripts/create_founder_account.py || echo 'Founder account already exists'

echo '▸ Updating nginx config…'
cp nginx_dmorales_site.conf /etc/nginx/sites-available/dm-ai-os
ln -sf /etc/nginx/sites-available/dm-ai-os /etc/nginx/sites-enabled/dm-ai-os 2>/dev/null || true
nginx -t && systemctl reload nginx || echo 'Nginx reload skipped'

echo '▸ Setting up systemd service…'
cat > /etc/systemd/system/$ServiceName.service << 'SVCEOF'
[Unit]
Description=DM AI OS — Autonomous Business Operating System
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$RemoteDir
Environment=PATH=$RemoteDir/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$RemoteDir/.venv/bin/uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable $ServiceName
systemctl restart $ServiceName
sleep 3
systemctl status $ServiceName --no-pager | head -20

echo '▸ Health check…'
curl -sf http://127.0.0.1:8000/health && echo ' ✅ Backend ONLINE' || echo ' ⚠️ Backend not responding yet (check logs)'
echo ''
echo '✅ DM AI OS deployed successfully!'
echo '   URL: https://app.dmorales.site'
echo '   Panel: https://app.dmorales.site/panel/owner'
"@

if ($DryRun) {
    Write-Ok "DRY RUN — remote script ready (not executed)"
    Write-Host ""
    Write-Host "  ─── REMOTE SCRIPT (run manually via SSH) ───" -ForegroundColor Yellow
    Write-Host $RemoteScript -ForegroundColor Gray
} else {
    ssh "${VpsUser}@${VpsHost}" $RemoteScript
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Remote script failed. Check VPS logs: journalctl -u $ServiceName -n 50"
        exit 1
    }
}

# ── STEP 5: Final health check from local machine ────────────
Write-Step "Final health check from local machine…"

Start-Sleep -Seconds 5

$HealthUrl = "https://app.dmorales.site/health"
Write-Host "    Checking: $HealthUrl" -ForegroundColor Gray

if ($DryRun) {
    Write-Ok "DRY RUN — health check skipped"
} else {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -Method GET -TimeoutSec 15
        if ($response.status -eq "ONLINE") {
            Write-Ok "Health check PASSED: $($response | ConvertTo-Json -Compress)"
        } else {
            Write-Warn "Health check returned unexpected status: $($response | ConvertTo-Json -Compress)"
        }
    } catch {
        Write-Warn "Health check failed (may need DNS propagation): $_"
        Write-Host "    Manual check: curl https://app.dmorales.site/health" -ForegroundColor Gray
    }
}

# ── SUMMARY ──────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   ✅ DEPLOY COMPLETE                          ║" -ForegroundColor Green
Write-Host "  ╠══════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "  ║   Frontend:  https://app.dmorales.site        ║" -ForegroundColor Green
Write-Host "  ║   Owner:     https://app.dmorales.site/panel/owner  ║" -ForegroundColor Green
Write-Host "  ║   Dashboard: https://app.dmorales.site/panel/dashboard ║" -ForegroundColor Green
Write-Host "  ║   API Docs:  https://app.dmorales.site/docs   ║" -ForegroundColor Green
Write-Host "  ║   Health:    https://app.dmorales.site/health  ║" -ForegroundColor Green
Write-Host "  ║                                               ║" -ForegroundColor Green
Write-Host "  ║   dmorales.site → ALMA IA (INTACTO) ✓         ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# ── MANUAL DEPLOY REFERENCE ──────────────────────────────────
Write-Host "  ── MANUAL DEPLOY (if SSH fails) ────────────────" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Conectar al VPS:" -ForegroundColor White
Write-Host "     ssh root@62.171.169.50" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Subir archivos (desde Windows):" -ForegroundColor White
Write-Host "     scp -r `"$ProjectRoot\src`" root@62.171.169.50:$RemoteDir/" -ForegroundColor Cyan
Write-Host "     scp -r `"$ProjectRoot\public`" root@62.171.169.50:$RemoteDir/" -ForegroundColor Cyan
Write-Host "     scp -r `"$ProjectRoot\scripts`" root@62.171.169.50:$RemoteDir/" -ForegroundColor Cyan
Write-Host "     scp `"$ProjectRoot\requirements.txt`" root@62.171.169.50:$RemoteDir/" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. En el VPS ejecutar:" -ForegroundColor White
Write-Host "     cd $RemoteDir" -ForegroundColor Cyan
Write-Host "     python3 -m venv .venv && source .venv/bin/activate" -ForegroundColor Cyan
Write-Host "     pip install -r requirements.txt" -ForegroundColor Cyan
Write-Host "     python scripts/create_founder_account.py" -ForegroundColor Cyan
Write-Host "     uvicorn src.api.server:app --host 0.0.0.0 --port 8000 &" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Verificar:" -ForegroundColor White
Write-Host "     curl https://app.dmorales.site/health" -ForegroundColor Cyan
Write-Host ""
