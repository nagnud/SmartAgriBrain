[CmdletBinding()]
param(
  [switch] $NoReload
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
$apiRoot = Join-Path $projectRoot "backend_api"
$venvRoot = Join-Path $apiRoot ".venv"
$pythonExe = Join-Path $venvRoot "Scripts\python.exe"
$codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$envPath = Join-Path $apiRoot ".env"
$envExamplePath = Join-Path $apiRoot ".env.example"
$requirementsPath = Join-Path $apiRoot "requirements.txt"
$dependencyStampPath = Join-Path $venvRoot ".requirements.sha256"

Set-Location -LiteralPath $apiRoot

if (-not (Test-Path -LiteralPath $envPath)) {
  Copy-Item -LiteralPath $envExamplePath -Destination $envPath
  Write-Host "Created backend_api\.env from .env.example."
  Write-Host "Set DEEPSEEK_API_KEY in backend_api\.env to enable real AI farm advice and assistant chat."
  Write-Host "Voice input is handled in the browser with the Web Speech API; no backend voice key is required."
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
  Write-Host "Creating backend Python virtual environment..."
  if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv $venvRoot
  } elseif (Test-Path -LiteralPath $codexPython) {
    & $codexPython -m venv $venvRoot
  } else {
    throw "Python was not found. Please install Python 3.10+ or use Codex bundled Python."
  }
}

$requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $dependencyStampPath) {
  (Get-Content -LiteralPath $dependencyStampPath -Raw).Trim()
} else {
  ""
}
if ($installedHash -ne $requirementsHash) {
  Write-Host "Installing backend dependencies because requirements.txt changed or has not been recorded..."
  & $pythonExe -m pip install -r $requirementsPath
  if ($LASTEXITCODE -ne 0) {
    throw "Backend dependency installation failed with exit code $LASTEXITCODE."
  }
  Set-Content -LiteralPath $dependencyStampPath -Value $requirementsHash -Encoding ascii
} else {
  Write-Host "Backend dependencies are current."
}

$envValues = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^\s*[^#].*=" }
foreach ($line in $envValues) {
  $key, $value = $line -split "=", 2
  [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
}

$hostValue = $env:API_HOST
$portValue = $env:API_PORT
if ([string]::IsNullOrWhiteSpace($hostValue)) {
  $hostValue = "0.0.0.0"
}
if ([string]::IsNullOrWhiteSpace($portValue)) {
  $portValue = "8000"
}

Write-Host "Starting FastAPI backend at http://localhost:$portValue ..."
$reloadArgs = @()
if (-not $NoReload -and $env:API_RELOAD -ne "false") {
    $reloadArgs += @(
        "--reload",
        "--reload-dir=$apiRoot",
        "--reload-exclude=.venv/*",
        "--reload-exclude=tests/*",
        "--reload-exclude=uploads/*",
        "--reload-exclude=position_captures/*",
        "--reload-exclude=__pycache__/*",
        "--reload-exclude=*.db",
        "--timeout-graceful-shutdown=3"
    )
  Write-Host "Development auto-reload is enabled. Python source changes will take effect automatically."
} else {
  Write-Host "Development auto-reload is disabled for this managed background process."
}
& $pythonExe -m uvicorn main:app --host $hostValue --port ([int]$portValue) @reloadArgs
