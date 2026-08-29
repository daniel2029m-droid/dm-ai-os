<#
.SYNOPSIS
Launches a Cloudflare Quick Tunnel for DM AI OS API Gateway.

.DESCRIPTION
Sanitizes existing cloudflared config files, downloads cloudflared.exe if not present, 
and starts a temporary Quick Tunnel exposing http://127.0.0.1:8000 to the public internet via HTTPS.
#>

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
Set-Location $rootDir

# Sanitization of cloudflared configs to allow Quick Tunnel
$cfConfigPaths = @(
    "$env:USERPROFILE\.cloudflared\config.yml",
    "$env:USERPROFILE\.cloudflared\config.yaml",
    "$env:APPDATA\cloudflared\config.yml",
    "$env:APPDATA\cloudflared\config.yaml",
    "$env:LOCALAPPDATA\cloudflared\config.yml",
    "$env:LOCALAPPDATA\cloudflared\config.yaml",
    "$rootDir\config.yml",
    "$rootDir\config.yaml"
)

foreach ($cfPath in $cfConfigPaths) {
    if (Test-Path $cfPath) {
        Write-Host "Backing up cloudflared config at $cfPath..." -ForegroundColor Yellow
        Rename-Item -Path $cfPath -NewName "$cfPath.bak" -Force -ErrorAction SilentlyContinue
    }
}

$CloudflaredUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
$CloudflaredPath = if (Test-Path "$rootDir\cloudflared.exe") { "$rootDir\cloudflared.exe" } else { "$scriptDir\cloudflared.exe" }

if (-not (Test-Path $CloudflaredPath)) {
    Write-Host "Downloading cloudflared.exe..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $CloudflaredUrl -OutFile $CloudflaredPath
}

Write-Host "Starting Cloudflare Quick Tunnel for http://127.0.0.1:8000..." -ForegroundColor Cyan
Write-Host "Please wait for the URL to be generated..." -ForegroundColor Yellow

$logFile = "$rootDir\cloudflared.log"
if (Test-Path $logFile) { Remove-Item $logFile -Force -ErrorAction SilentlyContinue }

$process = Start-Process -FilePath $CloudflaredPath -ArgumentList "tunnel --url http://127.0.0.1:8000" -NoNewWindow -PassThru -RedirectStandardError $logFile

$urlFound = $false
$retryCount = 0

while (-not $urlFound -and $retryCount -lt 30) {
    Start-Sleep -Seconds 2
    if (Test-Path $logFile) {
        $logContent = Get-Content $logFile -Tail 30 -ErrorAction SilentlyContinue
        foreach ($line in $logContent) {
            if ($line -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
                $url = $matches[0]
                [System.IO.File]::WriteAllText("$rootDir\tunnel_url.txt", $url)
                Write-Host ""
                Write-Host "==========================================================" -ForegroundColor Green
                Write-Host " DM AI OS Remote Access URL is ready:" -ForegroundColor Green
                Write-Host " $url" -ForegroundColor White -BackgroundColor DarkCyan
                Write-Host " Saved to: $rootDir\tunnel_url.txt" -ForegroundColor DarkGray
                Write-Host "==========================================================" -ForegroundColor Green
                Write-Host ""
                $urlFound = $true
                break
            }
        }
    }
    $retryCount++
}

if (-not $urlFound) {
    Write-Host "Could not find URL in logs. Check $logFile for details." -ForegroundColor Red
}

Write-Host "Tunnel process running (PID $($process.Id))..." -ForegroundColor Yellow
Wait-Process -Id $process.Id

