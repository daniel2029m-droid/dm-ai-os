<#
.SYNOPSIS  Phase 0.5 — Reuse Audit. Read-only. PS 5.1.
           Scans D:\, existing AI projects, Pinokio, LM Studio, venvs, node projects.
           Outputs structured JSON to Project_State/Audit/reuse/
.VERSION   1.0
#>

$ReuseDir = "$env:USERPROFILE\.gemini\antigravity-ide\scratch\Project_State\Audit\reuse"
New-Item -ItemType Directory -Force -Path $ReuseDir | Out-Null
$TS = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"

function Save-Json($obj, $name) {
    $path = Join-Path $ReuseDir $name
    $obj | ConvertTo-Json -Depth 10 | Out-File $path -Encoding UTF8
    $kb = [math]::Round((Get-Item $path).Length / 1KB, 1)
    Write-Host "[OK] $name ($kb KB)"
}

function Find-Recursive($root, $pattern, $depth=6, $maxResults=50) {
    if (-not (Test-Path $root)) { return @() }
    @(Get-ChildItem $root -Recurse -Depth $depth -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match $pattern } | Select-Object -First $maxResults |
      ForEach-Object { $_.FullName })
}

function Get-DirSize($path) {
    if (-not (Test-Path $path)) { return 0 }
    $size = (Get-ChildItem $path -Recurse -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
    [math]::Round($size / 1GB, 3)
}

function Read-JsonSafe($path) {
    try { return (Get-Content $path -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json) }
    catch { return $null }
}

# ── 1. D:\ DRIVE OVERVIEW ────────────────────────────────────────────────────
Write-Host "[..] D: drive overview"
$dDisk = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DeviceID -eq "D:" }
$dInfo = if ($dDisk) {
    @{ Found=$true; Size_GB=[math]::Round($dDisk.Size/1GB,2); Free_GB=[math]::Round($dDisk.FreeSpace/1GB,2) }
} else { @{ Found=$false } }

# Top-level D:\ directories
$dTopDirs = @()
if (Test-Path "D:\") {
    Get-ChildItem "D:\" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $dTopDirs += @{ Name=$_.Name; Path=$_.FullName }
    }
}
Save-Json @{ Timestamp=$TS; Drive=$dInfo; TopDirs=$dTopDirs } "d_drive.json"

# ── 2. PINOKIO INSPECTION ────────────────────────────────────────────────────
Write-Host "[..] Pinokio apps"
$pinokioApps = @()
$pinokioPaths = @("D:\pinokio\data","D:\pinokio_data","$env:USERPROFILE\pinokio")
foreach ($pp in $pinokioPaths) {
    $appDir = Join-Path $pp "apps"
    if (Test-Path $appDir) {
        Get-ChildItem $appDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $appPath = $_.FullName
            $appName = $_.Name
            # Check for key files
            $hasPinokio = Test-Path (Join-Path $appPath "pinokio.js")
            $hasInstall = Test-Path (Join-Path $appPath "install.js")
            $hasReqs    = Test-Path (Join-Path $appPath "requirements.txt")
            $hasApp     = Test-Path (Join-Path $appPath "app.py")
            $size       = Get-DirSize $appPath
            $pinokioApps += @{
                Name=$appName; Path=$appPath
                HasPinokioJs=$hasPinokio; HasInstallJs=$hasInstall
                HasRequirements=$hasReqs; HasAppPy=$hasApp
                Size_GB=$size
            }
        }
    }
    # Also check top-level for installed app folders
    if (Test-Path $pp) {
        Get-ChildItem $pp -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @("apps","models","cache","logs","bin") } |
        ForEach-Object {
            $pinokioApps += @{ Name=$_.Name; Path=$_.FullName; Source="root" }
        }
    }
}
Save-Json @{ Timestamp=$TS; PinokioPaths=$pinokioPaths; Apps=$pinokioApps } "pinokio.json"

# ── 3. LM STUDIO INSPECTION ──────────────────────────────────────────────────
Write-Host "[..] LM Studio"
$lmsPath = "D:\lmstudio\data"
$lmsModels = @()
$lmsModelDir = Join-Path $lmsPath "models"
if (Test-Path $lmsModelDir) {
    Get-ChildItem $lmsModelDir -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".gguf",".bin",".safetensors") } |
    Select-Object -First 50 | ForEach-Object {
        $lmsModels += @{ Name=$_.Name; Path=$_.FullName; Size_GB=[math]::Round($_.Length/1GB,3) }
    }
}
$lmsServerLog = Join-Path $lmsPath "logs"
Save-Json @{
    Timestamp=$TS; DataPath=$lmsPath
    ModelsDir=$lmsModelDir; Models=$lmsModels
    Size_GB=(Get-DirSize $lmsPath)
} "lmstudio.json"

# ── 4. EXISTING AI PROJECTS ──────────────────────────────────────────────────
Write-Host "[..] Existing AI projects"
$aiProjectPaths = @(
    "$env:USERPROFILE\Agente_Resultados",
    "$env:USERPROFILE\.gemini\antigravity\scratch\agent_bot",
    "$env:USERPROFILE\.gemini\antigravity\scratch\multi_agent_system",
    "$env:USERPROFILE\.agents",
    "$env:USERPROFILE\.bito\codeReviewAgent"
)
$projectReports = @()
foreach ($projPath in $aiProjectPaths) {
    if (-not (Test-Path $projPath)) {
        $projectReports += @{ Path=$projPath; Found=$false }
        continue
    }
    # Read key files
    $files = @(Get-ChildItem $projPath -Recurse -Depth 5 -ErrorAction SilentlyContinue |
               Select-Object -First 200 | ForEach-Object {
                   @{ Name=$_.Name; RelPath=$_.FullName.Replace($projPath,"").TrimStart("\"); IsDir=$_.PSIsContainer }
               })
    # Detect tech stack
    $hasPy      = ($files | Where-Object { $_.Name -match "\.py$" }).Count -gt 0
    $hasJs      = ($files | Where-Object { $_.Name -match "\.js$|\.ts$" }).Count -gt 0
    $hasReqs    = Test-Path (Join-Path $projPath "requirements.txt")
    $hasPkg     = Test-Path (Join-Path $projPath "package.json")
    $hasVenv    = Test-Path (Join-Path $projPath ".venv") -or (Test-Path (Join-Path $projPath "venv"))
    $hasDocker  = Test-Path (Join-Path $projPath "Dockerfile") -or (Test-Path (Join-Path $projPath "docker-compose.yml"))
    $hasMcp     = ($files | Where-Object { $_.Name -match "mcp" }).Count -gt 0
    $hasAgent   = ($files | Where-Object { $_.Name -match "agent" }).Count -gt 0
    $hasPrompts = ($files | Where-Object { $_.Name -match "prompt|system" }).Count -gt 0
    $hasN8n     = ($files | Where-Object { $_.Name -match "n8n|workflow" }).Count -gt 0
    # Read requirements if present
    $reqs = @()
    if ($hasReqs) {
        $reqs = @(Get-Content (Join-Path $projPath "requirements.txt") -ErrorAction SilentlyContinue |
                  Where-Object { $_.Trim() -and -not $_.StartsWith("#") })
    }
    # Read package.json if present
    $pkgJson = $null
    if ($hasPkg) { $pkgJson = Read-JsonSafe (Join-Path $projPath "package.json") }

    # Read README
    $readmePath = Get-ChildItem $projPath -Filter "README*" -ErrorAction SilentlyContinue | Select-Object -First 1
    $readme = if ($readmePath) { (Get-Content $readmePath.FullName -First 20 -ErrorAction SilentlyContinue) -join "`n" } else { $null }

    $projectReports += @{
        Path=$projPath; Found=$true; Name=(Split-Path $projPath -Leaf)
        FileCount=$files.Count; Size_GB=(Get-DirSize $projPath)
        Stack=@{ Python=$hasPy; JavaScript=$hasJs; HasRequirements=$hasReqs; HasPackageJson=$hasPkg; HasVenv=$hasVenv; HasDocker=$hasDocker }
        Has=@{ MCP=$hasMcp; Agent=$hasAgent; Prompts=$hasPrompts; N8N=$hasN8n }
        Requirements=$reqs; PackageJson=$pkgJson
        README=$readme
        Files=$files
    }
}
Save-Json @{ Timestamp=$TS; Projects=$projectReports } "existing_projects.json"

# ── 5. COMPONENT SEARCH ── llama.cpp, ComfyUI, Open WebUI, n8n, Playwright ──
Write-Host "[..] Component search (D:\, UserProfile, common paths)"
$searchRoots = @("D:\","$env:USERPROFILE","C:\tools","C:\apps","$env:LOCALAPPDATA\Programs")

$componentSearch = @{}

# llama.cpp
$llamaCandidates = @()
foreach ($root in @("D:\","$env:USERPROFILE","C:\")) {
    if (Test-Path $root) {
        Get-ChildItem $root -Recurse -Depth 4 -Filter "llama*" -ErrorAction SilentlyContinue |
        Select-Object -First 20 | ForEach-Object { $llamaCandidates += $_.FullName }
    }
}
$componentSearch["llama_cpp"] = $llamaCandidates

# ComfyUI
$comfyCandidates = @()
foreach ($root in $searchRoots) {
    if (Test-Path $root) {
        Get-ChildItem $root -Recurse -Depth 4 -Filter "ComfyUI*" -Directory -ErrorAction SilentlyContinue |
        Select-Object -First 10 | ForEach-Object { $comfyCandidates += $_.FullName }
        # also search in pinokio apps
        Get-ChildItem $root -Recurse -Depth 6 -Filter "comfy*" -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "pinokio|apps" } | Select-Object -First 10 |
        ForEach-Object { $comfyCandidates += $_.FullName }
    }
}
$componentSearch["comfyui"] = $comfyCandidates

# Open WebUI
$owCandidates = @()
foreach ($root in $searchRoots) {
    if (Test-Path $root) {
        Get-ChildItem $root -Recurse -Depth 5 -Filter "*open*webui*" -ErrorAction SilentlyContinue |
        Select-Object -First 10 | ForEach-Object { $owCandidates += $_.FullName }
        Get-ChildItem $root -Recurse -Depth 5 -Filter "*openwebui*" -ErrorAction SilentlyContinue |
        Select-Object -First 10 | ForEach-Object { $owCandidates += $_.FullName }
    }
}
$componentSearch["open_webui"] = $owCandidates

# n8n
$n8nCandidates = @()
$n8nSearchPaths = @(
    "$env:APPDATA\npm\node_modules\n8n",
    "$env:LOCALAPPDATA\n8n",
    "$env:USERPROFILE\n8n",
    "D:\n8n",
    "C:\n8n"
)
foreach ($p in $n8nSearchPaths) { if (Test-Path $p) { $n8nCandidates += $p } }
foreach ($root in $searchRoots) {
    if (Test-Path $root) {
        Get-ChildItem $root -Recurse -Depth 4 -Filter "n8n" -Directory -ErrorAction SilentlyContinue |
        Select-Object -First 10 | ForEach-Object { $n8nCandidates += $_.FullName }
    }
}
$componentSearch["n8n"] = ($n8nCandidates | Select-Object -Unique)

# Playwright
$pwCandidates = @()
$pwPyPkg = & pip show playwright 2>&1 | Out-String
$pwNodeGlobal = Test-Path "$env:APPDATA\npm\node_modules\playwright"
$pwUserlocal  = Test-Path "$env:USERPROFILE\.local\bin\playwright"
if ($pwPyPkg -match "Version") { $pwCandidates += "pip: $($pwPyPkg | Select-String 'Version')" }
if ($pwNodeGlobal) { $pwCandidates += "$env:APPDATA\npm\node_modules\playwright" }
if ($pwUserlocal)  { $pwCandidates += "$env:USERPROFILE\.local\bin\playwright" }
# Check in venvs
Find-Recursive $env:USERPROFILE "playwright" 5 20 | ForEach-Object { $pwCandidates += $_ }
$componentSearch["playwright"] = ($pwCandidates | Select-Object -Unique)

# MCP Servers
$mcpCandidates = @()
Find-Recursive $env:USERPROFILE "mcp" 5 30 | ForEach-Object { $mcpCandidates += $_ }
Find-Recursive "D:\" "mcp" 4 20 | ForEach-Object { $mcpCandidates += $_ }
$componentSearch["mcp_servers"] = ($mcpCandidates | Select-Object -Unique)

# Docker / docker-compose
$dockerCandidates = Find-Recursive $env:USERPROFILE "docker-compose" 5 20
Find-Recursive "D:\" "docker-compose" 4 10 | ForEach-Object { $dockerCandidates += $_ }
$componentSearch["docker_projects"] = ($dockerCandidates | Select-Object -Unique)

# Workflow files (n8n json, yaml)
$workflowFiles = @()
Find-Recursive $env:USERPROFILE "workflow" 5 30 | ForEach-Object { $workflowFiles += $_ }
Find-Recursive "D:\" "workflow" 4 20 | ForEach-Object { $workflowFiles += $_ }
$componentSearch["workflow_files"] = ($workflowFiles | Select-Object -Unique)

Save-Json @{ Timestamp=$TS; Components=$componentSearch } "component_search.json"

# ── 6. PYTHON PACKAGES REUSE SCAN ───────────────────────────────────────────
Write-Host "[..] Python packages reuse scan"
$pyAuditPath = "$env:USERPROFILE\.gemini\antigravity-ide\scratch\Project_State\Audit\python.json"
$pyData = Read-JsonSafe $pyAuditPath
$relevantPkgs = @()
$aiPkgPatterns = "langchain|openai|anthropic|ollama|llama|playwright|selenium|requests|aiohttp|fastapi|uvicorn|flask|pydantic|chromadb|faiss|qdrant|vector|embed|transformers|torch|PIL|image|comfy|n8n|mcp|agent|crew|autogen|gradio|streamlit|tiktoken|httpx|bs4|scrapy|selenium|pyppeteer"
if ($pyData -and $pyData.Packages) {
    $pyData.Packages | ForEach-Object {
        if ($_.Name -match $aiPkgPatterns) {
            $relevantPkgs += @{ Name=$_.Name; Version=$_.Version }
        }
    }
}
Save-Json @{ Timestamp=$TS; RelevantPackages=$relevantPkgs; TotalPackages=$pyData.PackageCount } "python_reuse.json"

# ── 7. VIRTUAL ENVIRONMENTS DEEP SCAN ───────────────────────────────────────
Write-Host "[..] Virtual environments"
$venvs = @()
$venvRoots = @($env:USERPROFILE,"D:\")
foreach ($root in $venvRoots) {
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem $root -Recurse -Depth 6 -Filter "pyvenv.cfg" -ErrorAction SilentlyContinue |
    Select-Object -First 30 | ForEach-Object {
        $venvPath = $_.DirectoryName
        $cfgContent = Get-Content $_.FullName -ErrorAction SilentlyContinue
        $pyVer = ($cfgContent | Select-String "version") | ForEach-Object { $_.Line }
        # Check site-packages
        $sitePkgs = Get-ChildItem (Join-Path $venvPath "Lib\site-packages") -Directory -ErrorAction SilentlyContinue |
                    Select-Object -First 100 | Where-Object { $_.Name -match $aiPkgPatterns } |
                    ForEach-Object { $_.Name }
        $venvs += @{ Path=$venvPath; PythonVersion=$pyVer; RelevantPackages=@($sitePkgs) }
    }
}
Save-Json @{ Timestamp=$TS; VirtualEnvs=$venvs } "venvs.json"

# ── 8. NODE PROJECTS SCAN ────────────────────────────────────────────────────
Write-Host "[..] Node projects"
$nodeProjects = @()
foreach ($root in @($env:USERPROFILE,"D:\")) {
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem $root -Recurse -Depth 5 -Filter "package.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "node_modules|\.gemini|AppData\\Local\\Programs|AppData\\Roaming\\npm" } |
    Select-Object -First 20 | ForEach-Object {
        $pkg = Read-JsonSafe $_.FullName
        if ($pkg) {
            $deps = @()
            if ($pkg.dependencies) { $pkg.dependencies.PSObject.Properties | ForEach-Object { $deps += "$($_.Name)@$($_.Value)" } }
            if ($pkg.devDependencies) { $pkg.devDependencies.PSObject.Properties | ForEach-Object { $deps += "dev:$($_.Name)" } }
            $nodeProjects += @{
                Path=$_.DirectoryName; Name=$pkg.name; Version=$pkg.version
                Description=$pkg.description; Dependencies=$deps
            }
        }
    }
}
Save-Json @{ Timestamp=$TS; Projects=$nodeProjects } "node_projects.json"

# ── 9. SCRIPTS & AUTOMATION SCAN ────────────────────────────────────────────
Write-Host "[..] Existing scripts and automation"
$scripts = @()
$scriptPatterns = "\.py$|\.ps1$|\.bat$|\.sh$|\.js$"
foreach ($root in @($env:USERPROFILE,"D:\")) {
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem $root -Recurse -Depth 5 -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match $scriptPatterns -and
                   $_.FullName -notmatch "node_modules|\.gemini|AppData\\Local\\Programs|__pycache__|site-packages" -and
                   $_.Name -match "agent|llm|ai|gpt|ollama|automation|workflow|scrape|browser|prompt|mcp|tool|facebook|content|publish|post|schedule" } |
    Select-Object -First 60 | ForEach-Object {
        $scripts += @{ Name=$_.Name; Path=$_.FullName; Size_KB=[math]::Round($_.Length/1KB,1); Ext=$_.Extension }
    }
}
Save-Json @{ Timestamp=$TS; Scripts=$scripts } "scripts.json"

# ── SUMMARY ──────────────────────────────────────────────────────────────────
$files = @(Get-ChildItem $ReuseDir -Filter "*.json" | ForEach-Object {
    @{ File=$_.Name; Size_KB=[math]::Round($_.Length/1KB,1) }
})
Save-Json @{ Timestamp=$TS; ReuseDir=$ReuseDir; Files=$files } "reuse_summary.json"

Write-Host "`n=== REUSE AUDIT COMPLETE ===" -ForegroundColor Green
Write-Host "Dir: $ReuseDir"
$files | ForEach-Object { Write-Host "  $($_.File) [$($_.Size_KB) KB]" }
