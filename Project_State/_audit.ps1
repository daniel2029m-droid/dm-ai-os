$out = [System.Text.StringBuilder]::new()
function log($s) { $out.AppendLine($s) | Out-Null }

log "=== AUDIT: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# OS
$os = Get-CimInstance Win32_OperatingSystem
log "`n[OS]"
log "Caption: $($os.Caption)"
log "Version: $($os.Version)"
log "Arch: $($os.OSArchitecture)"
log "RAM_Total_GB: $([math]::Round($os.TotalVisibleMemorySize/1MB,2))"
log "RAM_Free_GB: $([math]::Round($os.FreePhysicalMemory/1MB,2))"

# CPU
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
log "`n[CPU]"
log "Name: $($cpu.Name)"
log "Cores: $($cpu.NumberOfCores)"
log "Threads: $($cpu.NumberOfLogicalProcessors)"
log "MaxMHz: $($cpu.MaxClockSpeed)"

# GPU
log "`n[GPU]"
Get-CimInstance Win32_VideoController | ForEach-Object {
    log "Name: $($_.Name)"
    log "VRAM_MB: $([math]::Round($_.AdapterRAM/1MB,0))"
    log "Driver: $($_.DriverVersion)"
}

# Disk
log "`n[DISK]"
Get-CimInstance Win32_LogicalDisk | ForEach-Object {
    log "Drive: $($_.DeviceID) | Size_GB: $([math]::Round($_.Size/1GB,2)) | Free_GB: $([math]::Round($_.FreeSpace/1GB,2))"
}

# Motherboard + BIOS
$mb = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
log "`n[MOTHERBOARD]"
log "Manufacturer: $($mb.Manufacturer) | Product: $($mb.Product)"
log "`n[BIOS]"
log "Manufacturer: $($bios.Manufacturer) | Version: $($bios.SMBIOSBIOSVersion) | Date: $($bios.ReleaseDate)"

# Python
log "`n[PYTHON]"
$pyPath = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if ($pyPath) {
    $pyVer = & python --version 2>&1
    $pipVer = & pip --version 2>&1
    log "Path: $pyPath"
    log "Version: $pyVer"
    log "Pip: $pipVer"
    # Virtual envs
    $venvDirs = Get-ChildItem "$env:USERPROFILE" -Recurse -Depth 4 -Filter "pyvenv.cfg" -ErrorAction SilentlyContinue | Select-Object -First 20
    log "VirtualEnvs:"
    $venvDirs | ForEach-Object { log "  $($_.DirectoryName)" }
} else { log "NOT FOUND" }

# Node.js
log "`n[NODEJS]"
$nodeVer = & node --version 2>&1
$npmVer  = & npm --version 2>&1
if ($LASTEXITCODE -eq 0 -or $nodeVer -match '\d') {
    log "Node: $nodeVer"
    log "NPM: $npmVer"
    $npxVer = & npx --version 2>&1; log "NPX: $npxVer"
} else { log "NOT FOUND" }

# Git
log "`n[GIT]"
$gitVer = & git --version 2>&1
if ($gitVer -match 'git version') {
    log "$gitVer"
    $gitUser = & git config --global user.name 2>&1
    log "GlobalUser: $gitUser"
} else { log "NOT FOUND" }

# Docker
log "`n[DOCKER]"
$dockerVer = & docker --version 2>&1
if ($dockerVer -match 'Docker') {
    log "$dockerVer"
    $dockerPS = & docker ps 2>&1
    log "Running containers: $dockerPS"
} else { log "NOT FOUND" }

# WSL
log "`n[WSL]"
$wslList = & wsl --list --verbose 2>&1
log "$wslList"

# Ollama
log "`n[OLLAMA]"
$ollamaPath = (Get-Command ollama -ErrorAction SilentlyContinue)?.Source
if ($ollamaPath) {
    log "Path: $ollamaPath"
    $ollamaVer = & ollama --version 2>&1; log "Version: $ollamaVer"
    $ollamaModels = & ollama list 2>&1; log "Models:`n$ollamaModels"
} else { log "NOT FOUND" }

# llama.cpp
log "`n[LLAMA.CPP]"
$llamaPaths = @(
    "$env:USERPROFILE\llama.cpp",
    "C:\llama.cpp",
    "C:\tools\llama.cpp",
    "$env:USERPROFILE\AppData\Local\llama.cpp"
)
$llamaFound = $false
foreach ($p in $llamaPaths) {
    if (Test-Path $p) { log "Found: $p"; $llamaFound=$true }
}
$llamaExe = (Get-Command llama-cli -ErrorAction SilentlyContinue)?.Source
if ($llamaExe) { log "CLI: $llamaExe"; $llamaFound=$true }
if (-not $llamaFound) { log "NOT FOUND" }

# GGUF Models
log "`n[GGUF_MODELS]"
$ggufDirs = @("$env:USERPROFILE", "C:\models", "D:\models", "$env:USERPROFILE\models", "$env:USERPROFILE\.ollama\models")
$ggufFiles = @()
foreach ($d in $ggufDirs) {
    if (Test-Path $d) {
        $found = Get-ChildItem $d -Recurse -Filter "*.gguf" -ErrorAction SilentlyContinue | Select-Object -First 30
        $ggufFiles += $found
    }
}
if ($ggufFiles.Count -gt 0) {
    $ggufFiles | ForEach-Object { log "  $($_.FullName) [$([math]::Round($_.Length/1GB,2)) GB]" }
} else { log "NONE FOUND" }

# VS Code
log "`n[VSCODE]"
$codePath = (Get-Command code -ErrorAction SilentlyContinue)?.Source
if ($codePath) {
    $codeVer = & code --version 2>&1 | Select-Object -First 1
    log "Path: $codePath | Version: $codeVer"
    $extensions = & code --list-extensions 2>&1
    log "Extensions:`n$extensions"
} else { log "NOT FOUND" }

# Browsers
log "`n[BROWSERS]"
$browsers = @{
    Chrome  = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    Edge    = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
    Firefox = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
    Brave   = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
}
foreach ($b in $browsers.GetEnumerator()) {
    $exists = if ($b.Key -in @('Chrome','Edge','Firefox')) {
        Test-Path $b.Value
    } else { Test-Path $b.Value }
    log "$($b.Key): $(if($exists){'INSTALLED'} else {'NOT FOUND'})"
}

# n8n
log "`n[N8N]"
$n8nVer = & n8n --version 2>&1
if ($n8nVer -match '\d') { log "Version: $n8nVer" } else { log "NOT FOUND (CLI)" }
$n8nNpm = & npm list -g n8n --depth=0 2>&1
log "NPM global: $n8nNpm"

# ComfyUI
log "`n[COMFYUI]"
$comfyPaths = @("$env:USERPROFILE\ComfyUI","C:\ComfyUI","D:\ComfyUI","$env:USERPROFILE\Desktop\ComfyUI")
foreach ($p in $comfyPaths) {
    if (Test-Path $p) { log "Found: $p" }
}
$comfyProc = Get-Process | Where-Object { $_.Name -match "comfy" } | Select-Object -First 5
if ($comfyProc) { log "Running: $($comfyProc.Name)" } else { log "NOT RUNNING" }

# Open WebUI
log "`n[OPEN_WEBUI]"
$owPaths = @("$env:USERPROFILE\open-webui","C:\open-webui")
foreach ($p in $owPaths) { if (Test-Path $p) { log "Found: $p" } }
$owDocker = & docker ps --filter "name=open-webui" 2>&1
log "Docker: $owDocker"

# MCP Servers
log "`n[MCP_SERVERS]"
$mcpPaths = @(
    "$env:APPDATA\Claude\claude_desktop_config.json",
    "$env:USERPROFILE\.cursor\mcp.json",
    "$env:USERPROFILE\.config\mcp\config.json"
)
foreach ($p in $mcpPaths) {
    if (Test-Path $p) {
        log "Config: $p"
        log (Get-Content $p -Raw -ErrorAction SilentlyContinue)
    }
}

# Git Repos
log "`n[GIT_REPOS]"
$repoDirs = Get-ChildItem "$env:USERPROFILE" -Recurse -Depth 4 -Filter ".git" -Directory -ErrorAction SilentlyContinue | Select-Object -First 30
$repoDirs | ForEach-Object { log "  $($_.Parent.FullName)" }

# AI Projects (heuristic)
log "`n[AI_PROJECTS]"
$aiKeywords = @("agent","llm","ai","gpt","ollama","langchain","openai","crew","autogen","n8n","comfy","stable")
$aiDirs = Get-ChildItem "$env:USERPROFILE" -Depth 3 -Directory -ErrorAction SilentlyContinue | Where-Object {
    $name = $_.Name.ToLower()
    $aiKeywords | Where-Object { $name -match $_ }
} | Select-Object -First 30
$aiDirs | ForEach-Object { log "  $($_.FullName)" }

# Key Environment Variables
log "`n[ENV_VARS]"
$envKeys = @("OPENAI_API_KEY","ANTHROPIC_API_KEY","RUNPOD_API_KEY","HUGGINGFACE_TOKEN","GOOGLE_API_KEY",
             "REPLICATE_API_TOKEN","PATH","PYTHONPATH","VIRTUAL_ENV","CONDA_DEFAULT_ENV","OLLAMA_HOST",
             "OLLAMA_MODELS","COMFYUI_PATH","N8N_PORT")
foreach ($k in $envKeys) {
    $v = [System.Environment]::GetEnvironmentVariable($k)
    if ($v) {
        if ($k -match "KEY|TOKEN|SECRET") { log "$k = [SET - REDACTED]" }
        else { log "$k = $v" }
    } else { log "$k = NOT SET" }
}

# PowerShell version
log "`n[POWERSHELL]"
log "Version: $($PSVersionTable.PSVersion)"

# Existing Python packages (key ones)
log "`n[PYTHON_PACKAGES]"
$pkgs = & pip list 2>&1
log $pkgs

$result = $out.ToString()
$result | Out-File "$env:USERPROFILE\.gemini\antigravity-ide\scratch\Project_State\_raw_audit.txt" -Encoding UTF8
Write-Host "AUDIT COMPLETE. Lines: $($out.ToString().Split("`n").Count)"
Write-Host $result
