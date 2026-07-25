$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$backendScript = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "start-backend.ps1")).Path
$portValue = 8000

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $portValue -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
  $chain = @()
  $cursorPid = [int]$listener.OwningProcess
  $projectLauncherFound = $false

  for ($depth = 0; $depth -lt 8 -and $cursorPid -gt 0; $depth++) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $cursorPid" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
      break
    }
    $chain += $process
    if ([string]$process.CommandLine -like "*$backendScript*") {
      $projectLauncherFound = $true
      break
    }
    $cursorPid = [int]$process.ParentProcessId
  }

  $listenerProcess = $chain | Select-Object -First 1
  $isUvicorn = $null -ne $listenerProcess -and [string]$listenerProcess.CommandLine -match "uvicorn\s+main:app"
  if (-not $isUvicorn -or -not $projectLauncherFound) {
    throw "Port $portValue is occupied by a process that was not launched by this project's start-backend.ps1. It was left untouched."
  }

  Write-Host "Stopping the existing SmartAgriBrain backend process chain..."
  foreach ($process in $chain) {
    Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
  }
}

$portReleased = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
  if (-not (Get-NetTCPConnection -State Listen -LocalPort $portValue -ErrorAction SilentlyContinue)) {
    $portReleased = $true
    break
  }
  Start-Sleep -Milliseconds 250
}
if (-not $portReleased) {
  throw "Port $portValue was not released after stopping the old backend."
}

$logRoot = Join-Path $env:LOCALAPPDATA "SmartAgriBrain\logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $logRoot "backend-$runStamp.out.log"
$stderrLog = Join-Path $logRoot "backend-$runStamp.err.log"
$launcher = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
  "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendScript
) -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

$backendReady = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
  if (Get-NetTCPConnection -State Listen -LocalPort $portValue -ErrorAction SilentlyContinue) {
    $backendReady = $true
    break
  }
  Start-Sleep -Milliseconds 500
}
if (-not $backendReady) {
  throw "The new backend did not start on port $portValue. See $stderrLog."
}

Write-Host "SmartAgriBrain backend restarted successfully. Launcher PID: $($launcher.Id)"
Write-Host "API: http://127.0.0.1:$portValue"
Write-Host "Auto-reload: enabled"
Write-Host "Logs: $stdoutLog and $stderrLog"
