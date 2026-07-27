<#
.SYNOPSIS  Full system audit. Read-only. PS 5.1 compatible.
           pip packages collected with timeout. No blocking calls.
.VERSION   1.2 - Fixed: pip timeout, no inline $ stripping
#>
param([switch]$Force)

$AuditDir = "$env:USERPROFILE\.gemini\antigravity-ide\scratch\Project_State\Audit"
New-Item -ItemType Directory -Force -Path $AuditDir | Out-Null
$TS = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"

function Is-Fresh($file) {
    if ($Force) { return $false }
    if (-not (Test-Path $file)) { return $false }
    return ((Get-Date) - (Get-Item $file).LastWriteTime).TotalHours -lt 24
}
function Save-Json($obj, $name) {
    $path = Join-Path $AuditDir $name
    $obj | ConvertTo-Json -Depth 10 | Out-File $path -Encoding UTF8
    $kb = [math]::Round((Get-Item $path).Length / 1KB, 1)
    Write-Host "[OK] $name ($kb KB)"
}
function Get-ExePath($name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source } else { return $null }
}
function Run-Safe {
    param($exe, [string[]]$args2, $timeoutSec=15)
    try {
        $p = Start-Process -FilePath $exe -ArgumentList $args2 `
             -NoNewWindow -PassThru -RedirectStandardOutput "$env:TEMP\_out.txt" `
             -RedirectStandardError "$env:TEMP\_err.txt"
        $finished = $p.WaitForExit($timeoutSec * 1000)
        if (-not $finished) { $p.Kill(); return "TIMEOUT after ${timeoutSec}s" }
        return (Get-Content "$env:TEMP\_out.txt" -Raw -ErrorAction SilentlyContinue).Trim()
    } catch { return "ERROR: $_" }
}

# ── 1. HARDWARE ──────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "hardware.json"))) {
    Write-Host "[..] hardware"
    $os   = Get-CimInstance Win32_OperatingSystem
    $cpu  = Get-CimInstance Win32_Processor | Select-Object -First 1
    $mb   = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
    $bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
    $gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object {
        @{ Name=$_.Name; VRAM_MB=[math]::Round($_.AdapterRAM/1MB,0); Driver=$_.DriverVersion }
    })
    $disks = @(Get-CimInstance Win32_LogicalDisk | ForEach-Object {
        @{ Drive=$_.DeviceID; Size_GB=[math]::Round($_.Size/1GB,2); Free_GB=[math]::Round($_.FreeSpace/1GB,2) }
    })
    Save-Json @{
        Timestamp = $TS
        OS  = @{ Caption=$os.Caption; Version=$os.Version; Arch=$os.OSArchitecture; Build=$os.BuildNumber }
        RAM = @{ Total_GB=[math]::Round($os.TotalVisibleMemorySize/1MB,2); Free_GB=[math]::Round($os.FreePhysicalMemory/1MB,2) }
        CPU = @{ Name=$cpu.Name; Cores=$cpu.NumberOfCores; Threads=$cpu.NumberOfLogicalProcessors; MaxMHz=$cpu.MaxClockSpeed }
        GPU = $gpus; Disk = $disks
        Motherboard = @{ Manufacturer=$mb.Manufacturer; Product=$mb.Product }
        BIOS = @{ Manufacturer=$bios.Manufacturer; Version=$bios.SMBIOSBIOSVersion }
    } "hardware.json"
} else { Write-Host "[SKIP] hardware.json" }

# ── 2. PYTHON ────────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "python.json"))) {
    Write-Host "[..] python"
    $pyExe = Get-ExePath "python"
    if ($pyExe) {
        $pyVer  = Run-Safe $pyExe "--version" 10
        $pipExe = Get-ExePath "pip"
        $pipVer = if ($pipExe) { Run-Safe $pipExe "--version" 10 } else { "NOT FOUND" }
        # pip list plain text (fast, no JSON parse overhead)
        $pkgRaw = Run-Safe $pipExe "list" 30
        $pkgs = @()
        ($pkgRaw -split "`n") | Select-Object -Skip 2 | Where-Object { $_.Trim() } | ForEach-Object {
            $cols = $_.Trim() -split "\s+"
            if ($cols.Count -ge 2) { $pkgs += @{ Name=$cols[0]; Version=$cols[1] } }
        }
        $venvs = @(Get-ChildItem $env:USERPROFILE -Recurse -Depth 5 -Filter "pyvenv.cfg" -ErrorAction SilentlyContinue |
                   Select-Object -First 20 | ForEach-Object { $_.DirectoryName })
        $condaExe = Get-ExePath "conda"
        $condaVer = if ($condaExe) { Run-Safe $condaExe "--version" 10 } else { $null }
        Save-Json @{
            Timestamp=  $TS; Found=$true; Path=$pyExe; Version=$pyVer
            PipVersion= $pipVer; PackageCount=$pkgs.Count; Packages=$pkgs
            VirtualEnvs=$venvs; Conda=$condaVer
        } "python.json"
    } else {
        Save-Json @{ Timestamp=$TS; Found=$false } "python.json"
    }
} else { Write-Host "[SKIP] python.json" }

# ── 3. NODE.JS ───────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "node.json"))) {
    Write-Host "[..] node"
    $nodeExe = Get-ExePath "node"
    if ($nodeExe) {
        $nodeVer = (Run-Safe $nodeExe "--version" 10) -replace "v",""
        $npmExe  = Get-ExePath "npm"
        $npmVer  = if ($npmExe) { Run-Safe $npmExe "--version" 10 } else { "NOT FOUND" }
        $globRaw = if ($npmExe) { Run-Safe $npmExe @("list","-g","--depth=0") 30 } else { "" }
        $globals = @($globRaw -split "`n" | Where-Object { $_.Trim() -match "^[+`\\]" -or $_.Trim() -match "@" } | ForEach-Object { $_.Trim() -replace "^[+`\\-]+ ","" })
        Save-Json @{
            Timestamp=$TS; Found=$true; Path=$nodeExe
            NodeVersion=$nodeVer; NpmVersion=$npmVer; GlobalPackages=$globals
        } "node.json"
    } else { Save-Json @{ Timestamp=$TS; Found=$false } "node.json" }
} else { Write-Host "[SKIP] node.json" }

# ── 4. SOFTWARE ──────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "software.json"))) {
    Write-Host "[..] software (git/docker/wsl/vscode/browsers/n8n/comfy/mcp)"

    $gitExe = Get-ExePath "git"
    $gitData = if ($gitExe) {
        @{ Found=$true; Path=$gitExe
           Version=(Run-Safe $gitExe "--version" 10)
           User=(Run-Safe $gitExe @("config","--global","user.name") 5)
           Email=(Run-Safe $gitExe @("config","--global","user.email") 5) }
    } else { @{ Found=$false } }

    $dockerExe = Get-ExePath "docker"
    $dockerData = if ($dockerExe) {
        $cRaw = Run-Safe $dockerExe @("ps","--format","{{.Names}} | {{.Image}} | {{.Status}}") 15
        @{ Found=$true; Version=(Run-Safe $dockerExe "--version" 10)
           RunningContainers=@($cRaw -split "`n" | Where-Object { $_.Trim() }) }
    } else { @{ Found=$false } }

    $wslRaw = Run-Safe "wsl" @("--list","--verbose") 10
    $wslDistros = @($wslRaw -split "`n" | Select-Object -Skip 1 | Where-Object { $_.Trim() })

    $codeExe = Get-ExePath "code"
    $vscodeData = if ($codeExe) {
        $exts = @(Run-Safe $codeExe "--list-extensions" 20 -split "`n" | Where-Object { $_.Trim() })
        @{ Found=$true; Path=$codeExe; Extensions=$exts }
    } else { @{ Found=$false } }

    $browsers = @{}
    @{ Chrome="HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
       Edge="HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
       Firefox="HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
       Brave="$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
       Opera="$env:LOCALAPPDATA\Programs\Opera\opera.exe" }.GetEnumerator() | ForEach-Object {
        $browsers[$_.Key] = (Test-Path $_.Value)
    }

    $n8nExe = Get-ExePath "n8n"
    $n8nData = @{ CLI_Found=($null -ne $n8nExe)
                  Version=if($n8nExe){Run-Safe $n8nExe "--version" 10}else{$null} }

    $comfyRoots = @("$env:USERPROFILE\ComfyUI","C:\ComfyUI","D:\ComfyUI",
                    "$env:USERPROFILE\Desktop\ComfyUI","$env:USERPROFILE\Documents\ComfyUI")
    $comfyFound = @($comfyRoots | Where-Object { Test-Path $_ })

    $owRoots = @("$env:USERPROFILE\open-webui","C:\open-webui","$env:LOCALAPPDATA\open-webui")
    $owFound  = @($owRoots | Where-Object { Test-Path $_ })

    $mcpPaths = @(
        "$env:APPDATA\Claude\claude_desktop_config.json",
        "$env:USERPROFILE\.cursor\mcp.json",
        "$env:USERPROFILE\.config\mcp\config.json",
        "$env:APPDATA\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json"
    )
    $mcpConfigs = @{}
    foreach ($p in $mcpPaths) {
        if (Test-Path $p) {
            try { $mcpConfigs[$p] = (Get-Content $p -Raw | ConvertFrom-Json) }
            catch { $mcpConfigs[$p] = "PARSE_ERROR" }
        }
    }

    Save-Json @{
        Timestamp=$TS; Git=$gitData; Docker=$dockerData
        WSL=@{ Distros=$wslDistros }; VSCode=$vscodeData
        PowerShell=@{ Version=$PSVersionTable.PSVersion.ToString() }
        Browsers=$browsers; N8N=$n8nData
        ComfyUI=@{ Found=($comfyFound.Count -gt 0); Paths=$comfyFound }
        OpenWebUI=@{ Found=($owFound.Count -gt 0); Paths=$owFound }
        MCP=$mcpConfigs
    } "software.json"
} else { Write-Host "[SKIP] software.json" }

# ── 5. OLLAMA ────────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "ollama.json"))) {
    Write-Host "[..] ollama"
    $ollamaExe = Get-ExePath "ollama"
    if ($ollamaExe) {
        $ver = Run-Safe $ollamaExe "--version" 10
        $listRaw = Run-Safe $ollamaExe "list" 15
        $models = @()
        ($listRaw -split "`n") | Select-Object -Skip 1 | Where-Object { $_.Trim() } | ForEach-Object {
            $cols = $_ -split "\s{2,}"
            if ($cols.Count -ge 3) { $models += @{ Name=$cols[0].Trim(); ID=$cols[1].Trim(); Size=$cols[2].Trim() } }
        }
        $ollamaHost = [System.Environment]::GetEnvironmentVariable("OLLAMA_HOST")
        $ollamaModDir = [System.Environment]::GetEnvironmentVariable("OLLAMA_MODELS")
        Save-Json @{
            Timestamp=$TS; Found=$true; Path=$ollamaExe; Version=$ver
            Host=if($ollamaHost){$ollamaHost}else{"localhost:11434"}
            ModelsDir=if($ollamaModDir){$ollamaModDir}else{"$env:USERPROFILE\.ollama\models"}
            Models=$models
        } "ollama.json"
    } else { Save-Json @{ Timestamp=$TS; Found=$false } "ollama.json" }
} else { Write-Host "[SKIP] ollama.json" }

# ── 6. MODELS (GGUF scan) ────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "models.json"))) {
    Write-Host "[..] models (gguf scan)"
    $ggufRoots = @($env:USERPROFILE,"C:\models","D:\models",
                   "$env:USERPROFILE\models","$env:USERPROFILE\.ollama",
                   "$env:USERPROFILE\llama.cpp\models","$env:USERPROFILE\Documents\models")
    $ggufFiles = @()
    foreach ($root in $ggufRoots) {
        if (Test-Path $root) {
            Get-ChildItem $root -Recurse -Filter "*.gguf" -ErrorAction SilentlyContinue |
            Select-Object -First 30 | ForEach-Object {
                $ggufFiles += @{ Name=$_.Name; Path=$_.FullName; Size_GB=[math]::Round($_.Length/1GB,3) }
            }
        }
    }
    $llamaRoots = @("$env:USERPROFILE\llama.cpp","C:\llama.cpp","D:\llama.cpp","$env:LOCALAPPDATA\llama.cpp")
    $llamaFound = @($llamaRoots | Where-Object { Test-Path $_ })
    Save-Json @{
        Timestamp=$TS; GGUF_Files=$ggufFiles
        LlamaCpp=@{ Paths=$llamaFound; CLI=(Get-ExePath "llama-cli"); Server=(Get-ExePath "llama-server") }
    } "models.json"
} else { Write-Host "[SKIP] models.json" }

# ── 7. ENVIRONMENT ───────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "environment.json"))) {
    Write-Host "[..] environment"
    $sensitiveRx = "KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL"
    $allEnv = [System.Environment]::GetEnvironmentVariables()
    $envOut = @{}
    foreach ($k in ($allEnv.Keys | Sort-Object)) {
        $envOut[$k] = if ($k -match $sensitiveRx) { "[REDACTED]" } else { $allEnv[$k] }
    }
    $flagKeys = @("OPENAI_API_KEY","ANTHROPIC_API_KEY","RUNPOD_API_KEY","HUGGINGFACE_TOKEN",
                  "GOOGLE_API_KEY","REPLICATE_API_TOKEN","TOGETHER_API_KEY","GROQ_API_KEY",
                  "OLLAMA_HOST","OLLAMA_MODELS","PYTHONPATH","VIRTUAL_ENV","N8N_PORT")
    $flags = @{}
    foreach ($k in $flagKeys) {
        $v = [System.Environment]::GetEnvironmentVariable($k)
        $flags[$k] = if ($v) { "SET" } else { "NOT_SET" }
    }
    Save-Json @{ Timestamp=$TS; KeyStatus=$flags; AllVars=$envOut } "environment.json"
} else { Write-Host "[SKIP] environment.json" }

# ── 8. NETWORK ───────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "network.json"))) {
    Write-Host "[..] network"
    $adapters = @(Get-NetIPAddress -ErrorAction SilentlyContinue |
                  Where-Object { $_.AddressFamily -eq "IPv4" -and $_.IPAddress -ne "127.0.0.1" } |
                  ForEach-Object { @{ Interface=$_.InterfaceAlias; IP=$_.IPAddress } })
    $listening = @(& netstat -ano 2>&1 | Select-String "LISTENING" |
                   Select-Object -First 60 | ForEach-Object { $_.Line.Trim() })
    Save-Json @{ Timestamp=$TS; Adapters=$adapters; ListeningPorts=$listening } "network.json"
} else { Write-Host "[SKIP] network.json" }

# ── 9. PROJECTS ──────────────────────────────────────────────────────────────
if (-not (Is-Fresh (Join-Path $AuditDir "projects.json"))) {
    Write-Host "[..] git repos + AI projects"
    $repos = @()
    Get-ChildItem $env:USERPROFILE -Recurse -Depth 5 -Filter ".git" -Directory -ErrorAction SilentlyContinue |
    Select-Object -First 40 | ForEach-Object {
        $rp = $_.Parent.FullName
        $remote = (Run-Safe $gitExe @("-C",$rp,"remote","get-url","origin") 5)
        $repos += @{ Path=$rp; Remote=$remote }
    }
    $aiRx = "agent|llm|\bai\b|gpt|ollama|langchain|openai|crewai|autogen|n8n|comfy|stable|hugging|whisper|diffusion|embedding|vector|rag|chatbot"
    $aiProjects = @(Get-ChildItem $env:USERPROFILE -Depth 4 -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match $aiRx } | Select-Object -First 30 |
                    ForEach-Object { $_.FullName })
    Save-Json @{ Timestamp=$TS; GitRepos=$repos; AIProjects=$aiProjects } "projects.json"
} else { Write-Host "[SKIP] projects.json" }

# ── SUMMARY ──────────────────────────────────────────────────────────────────
$files = @(Get-ChildItem $AuditDir -Filter "*.json" | ForEach-Object {
    @{ File=$_.Name; Size_KB=[math]::Round($_.Length/1KB,1); Written=$_.LastWriteTime.ToString("HH:mm:ss") }
})
Save-Json @{ Timestamp=$TS; AuditDir=$AuditDir; Files=$files } "audit_summary.json"

Write-Host "`n=== AUDIT COMPLETE ===" -ForegroundColor Green
Write-Host "Dir: $AuditDir"
$files | ForEach-Object { Write-Host "  $($_.File) [$($_.Size_KB)KB]" }
