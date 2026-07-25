$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
  return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
}

function Update-CurrentPath {
  $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $extraPaths = @(
    "$env:ProgramFiles\nodejs",
    "$env:LOCALAPPDATA\Programs\Python\Python312",
    "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
    "$env:ProgramFiles\Python312",
    "$env:ProgramFiles\Python312\Scripts"
  )

  $env:Path = (@($machinePath, $userPath) + $extraPaths | Where-Object { $_ }) -join ";"
}

function Install-WingetPackage {
  param(
    [Parameter(Mandatory = $true)][string]$PackageId,
    [Parameter(Mandatory = $true)][string]$DisplayName
  )

  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "$DisplayName was not found, and winget is unavailable. Install $DisplayName manually, then run this script again."
  }

  Write-Host "$DisplayName was not found. Installing with winget..."
  Write-Host "If Windows asks for permission, choose Yes."
  & winget install --id $PackageId --exact --source winget --accept-package-agreements --accept-source-agreements --silent
  if ($LASTEXITCODE -ne 0) {
    throw "winget failed to install $DisplayName. Install it manually, then run this script again."
  }

  Update-CurrentPath
}

function Find-NodeTools {
  param([Parameter(Mandatory = $true)][string]$ProjectRoot)

  $workspaceRoot = Split-Path (Split-Path $ProjectRoot -Parent) -Parent
  $candidates = @(
    @{
      Node = Join-Path $workspaceRoot ".tools\node-v22.23.1-win-x64\node.exe"
      Npm = Join-Path $workspaceRoot ".tools\node-v22.23.1-win-x64\npm.cmd"
      Label = "project Node.js 22"
    },
    @{
      Node = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
      Npm = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\npm.cmd"
      Label = "Codex bundled Node"
    }
  )

  foreach ($candidate in $candidates) {
    if ((Test-Path -LiteralPath $candidate.Node) -and (Test-Path -LiteralPath $candidate.Npm)) {
      return [pscustomobject]$candidate
    }
  }

  $programFilesNode = Join-Path $env:ProgramFiles "nodejs\node.exe"
  $programFilesNpm = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
  if ((Test-Path -LiteralPath $programFilesNode) -and (Test-Path -LiteralPath $programFilesNpm)) {
    return [pscustomobject]@{
      Node = $programFilesNode
      Npm = $programFilesNpm
      Label = "installed Node.js"
    }
  }

  $systemNode = Get-Command node -ErrorAction SilentlyContinue
  $systemNpm = Get-Command npm -ErrorAction SilentlyContinue
  if ($systemNode -and $systemNpm) {
    return [pscustomobject]@{
      Node = $systemNode.Source
      Npm = $systemNpm.Source
      Label = "system Node"
    }
  }

  return $null
}

function Find-Python {
  $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  $python312User = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
  $python312Machine = Join-Path $env:ProgramFiles "Python312\python.exe"
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return [pscustomobject]@{ Command = "py"; Args = @("-3"); Label = "Python launcher" }
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return [pscustomobject]@{ Command = "python"; Args = @(); Label = "system Python" }
  }
  if (Test-Path -LiteralPath $python312User) {
    return [pscustomobject]@{ Command = $python312User; Args = @(); Label = "installed Python 3.12" }
  }
  if (Test-Path -LiteralPath $python312Machine) {
    return [pscustomobject]@{ Command = $python312Machine; Args = @(); Label = "installed Python 3.12" }
  }
  if (Test-Path -LiteralPath $codexPython) {
    return [pscustomobject]@{ Command = $codexPython; Args = @(); Label = "Codex bundled Python" }
  }

  return $null
}

function Ensure-NodeTools {
  param([Parameter(Mandatory = $true)][string]$ProjectRoot)

  Update-CurrentPath
  $nodeTools = Find-NodeTools -ProjectRoot $ProjectRoot
  if ($nodeTools) {
    Write-Host "Node.js OK: $($nodeTools.Label)"
    return $nodeTools
  }

  Install-WingetPackage -PackageId "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS"
  $nodeTools = Find-NodeTools -ProjectRoot $ProjectRoot
  if ($nodeTools) {
    Write-Host "Node.js OK: $($nodeTools.Label)"
    return $nodeTools
  }

  throw "Node.js was installed, but this PowerShell process cannot find node/npm. Close this window and double-click 一键启动.bat again."
}

function Ensure-Python {
  Update-CurrentPath
  $python = Find-Python
  if ($python) {
    Write-Host "Python OK: $($python.Label)"
    return $python
  }

  Install-WingetPackage -PackageId "Python.Python.3.12" -DisplayName "Python 3.12"
  $python = Find-Python
  if ($python) {
    Write-Host "Python OK: $($python.Label)"
    return $python
  }

  throw "Python was installed, but this PowerShell process cannot find it. Close this window and double-click 一键启动.bat again."
}

function Ensure-FrontendEnv {
  param([Parameter(Mandatory = $true)][string]$ProjectRoot)

  $envLocal = Join-Path $ProjectRoot ".env.local"
  if (Test-Path -LiteralPath $envLocal) {
    return
  }

  @(
    "VITE_API_BASE_URL=http://localhost:8000"
    "VITE_SITE_ID=greenhouse_001"
  ) | Set-Content -LiteralPath $envLocal -Encoding UTF8
  Write-Host "Created .env.local with portable local defaults."
}

function Ensure-BackendEnv {
  param([Parameter(Mandatory = $true)][string]$BackendRoot)

  $envPath = Join-Path $BackendRoot ".env"
  $examplePath = Join-Path $BackendRoot ".env.example"
  if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath $examplePath -Destination $envPath
    Write-Host "Created backend_api\.env from .env.example."
  }
}

function Ensure-BackendVenv {
  param(
    [Parameter(Mandatory = $true)][string]$BackendRoot,
    [Parameter(Mandatory = $true)]$Python
  )

  $venvRoot = Join-Path $BackendRoot ".venv"
  $pythonExe = Join-Path $venvRoot "Scripts\python.exe"
  $requirementsPath = Join-Path $BackendRoot "requirements.txt"
  $dependencyStampPath = Join-Path $venvRoot ".requirements.sha256"
  if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host "Creating backend Python virtual environment with $($Python.Label)..."
    & $Python.Command @($Python.Args + @("-m", "venv", $venvRoot))
  }

  $requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
  $installedHash = if (Test-Path -LiteralPath $dependencyStampPath) {
    (Get-Content -LiteralPath $dependencyStampPath -Raw).Trim()
  } else {
    ""
  }
  if ($installedHash -ne $requirementsHash) {
    Write-Host "Installing backend dependencies..."
    & $pythonExe -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
      throw "Backend dependency installation failed with exit code $LASTEXITCODE."
    }
    Set-Content -LiteralPath $dependencyStampPath -Value $requirementsHash -Encoding ascii
  } else {
    Write-Host "Backend dependencies are current."
  }
}

function Ensure-FrontendDependencies {
  param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)]$NodeTools
  )

  $viteCli = Join-Path $ProjectRoot "node_modules\vite\bin\vite.js"
  if (Test-Path -LiteralPath $viteCli) {
    return
  }

  Write-Host "Installing frontend dependencies with $($NodeTools.Label)..."
  Push-Location -LiteralPath $ProjectRoot
  try {
    & $NodeTools.Npm install
  } finally {
    Pop-Location
  }
}

function Get-PrimaryIPv4 {
  $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
      $_.IPAddress -notlike "127.*" -and
      $_.IPAddress -notlike "169.254.*" -and
      $_.PrefixOrigin -ne "WellKnown"
    } |
    Sort-Object InterfaceMetric |
    Select-Object -ExpandProperty IPAddress
  if ($addresses) {
    return @($addresses)[0]
  }
  return "127.0.0.1"
}

$projectRoot = Resolve-ProjectRoot
$backendRoot = Join-Path $projectRoot "backend_api"
$logRoot = Join-Path $env:LOCALAPPDATA "SmartAgriBrain\portable-logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

Write-Host "Project: $projectRoot"

$nodeTools = Ensure-NodeTools -ProjectRoot $projectRoot
$python = Ensure-Python

Ensure-FrontendEnv -ProjectRoot $projectRoot
Ensure-BackendEnv -BackendRoot $backendRoot
Ensure-FrontendDependencies -ProjectRoot $projectRoot -NodeTools $nodeTools
Ensure-BackendVenv -BackendRoot $backendRoot -Python $python

$fullStackScript = Join-Path $projectRoot "scripts\dev\start-full-stack.ps1"

Write-Host "Starting managed backend and frontend..."
& $fullStackScript

$ip = Get-PrimaryIPv4
Write-Host ""
Write-Host "Started."
Write-Host "Backend: http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"
Write-Host "Other devices on the same LAN can try: http://$ip`:5173"
Write-Host "Stop with scripts\dev\stop-full-stack.ps1 or 一键关闭.bat."
Write-Host ""
Write-Host "If ESP32/MQTT is needed on this new computer, use this LAN IP in the ESP32/Broker configuration: $ip"
