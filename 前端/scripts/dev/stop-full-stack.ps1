[CmdletBinding()]
param(
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths

$runtimeRoot = Join-Path $env:LOCALAPPDATA "SmartAgriBrain"
$statePath = Join-Path $runtimeRoot "full-stack.json"
$backendScript = (Join-Path $paths.Frontend "scripts\backend\start-backend.ps1").ToLowerInvariant()
$frontendScript = (Join-Path $paths.Frontend "scripts\web\start-web.ps1").ToLowerInvariant()

function Get-ProcessInfo {
    param([int] $ProcessId)
    if ($ProcessId -le 0) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-ManagedProcess {
    param(
        [object] $Process,
        [ValidateSet("backend", "frontend", "launcher")] [string] $Role
    )
    if ($null -eq $Process) { return $false }
    $commandLine = ([string]$Process.CommandLine).ToLowerInvariant()
    if ($Role -eq "backend") {
        return $commandLine -match "uvicorn\s+main:app"
    }
    if ($Role -eq "frontend") {
        return $commandLine -match "vite(?:\.js)?\s" -and $commandLine -match "(?:--port\s+|--port=)5173"
    }
    return $commandLine.Contains($backendScript) -or $commandLine.Contains($frontendScript)
}

function Stop-ProcessTree {
    param([int] $ProcessId, [string] $Role)
    $process = Get-ProcessInfo -ProcessId $ProcessId
    if ($null -eq $process) { return }

    if (-not $Quiet) {
        Write-Host "Stopping $Role process tree (PID $ProcessId)..."
    }
    & taskkill.exe /PID "$ProcessId" /T /F 2>&1 | Out-Null
    $taskkillExitCode = $LASTEXITCODE
    if ($taskkillExitCode -ne 0 -and -not $Quiet) {
        Write-Warning "$Role PID $ProcessId returned taskkill exit code $taskkillExitCode."
    }
}

function Get-ManagedTargets {
    $targets = @{}
    $unknown = @()

    # Exact launcher command lines let cleanup work even before either service
    # has opened its port.
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if (Test-ManagedProcess -Process $process -Role "launcher") {
            $targets[[int]$process.ProcessId] = "launcher"
        }
    }

    foreach ($listener in @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8000, 5173 })) {
        $role = if ([int]$listener.LocalPort -eq 8000) { "backend" } else { "frontend" }
        $process = Get-ProcessInfo -ProcessId ([int]$listener.OwningProcess)
        if (Test-ManagedProcess -Process $process -Role $role) {
            $targets[[int]$listener.OwningProcess] = $role
        } else {
            $unknown += [pscustomobject]@{
                Port = [int]$listener.LocalPort
                ProcessId = [int]$listener.OwningProcess
                Name = if ($process) { [string]$process.Name } else { "unknown" }
                CommandLine = if ($process) { [string]$process.CommandLine } else { "" }
            }
        }
    }

    [pscustomobject]@{ Targets = $targets; Unknown = $unknown }
}

# State is useful but not authoritative. Validate every stored PID before
# stopping it because Windows may reuse a stale PID for an unrelated process.
if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        foreach ($property in @("backend_launcher_pid", "frontend_launcher_pid")) {
            $storedPid = [int]($state.$property)
            $process = Get-ProcessInfo -ProcessId $storedPid
            if (Test-ManagedProcess -Process $process -Role "launcher") {
                Stop-ProcessTree -ProcessId $storedPid -Role $property
            }
        }
    } catch {
        if (-not $Quiet) {
            Write-Warning "The state file is invalid; continuing with process and port discovery."
        }
    }
}

# Repeat discovery because a reloader can replace a worker while shutdown is
# in progress. New managed background starts no longer enable reload, but this
# loop also cleans installations started with the older script.
$unknownListeners = @()
for ($pass = 0; $pass -lt 4; $pass++) {
    $discovered = Get-ManagedTargets
    $unknownListeners = @($discovered.Unknown)
    foreach ($entry in $discovered.Targets.GetEnumerator()) {
        Stop-ProcessTree -ProcessId ([int]$entry.Key) -Role ([string]$entry.Value)
    }
    if ($discovered.Targets.Count -eq 0) { break }
    Start-Sleep -Milliseconds 350
}

Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 350

$remaining = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8000, 5173 } |
    Select-Object LocalAddress, LocalPort, OwningProcess)
if ($remaining.Count -gt 0) {
    Write-Warning "Port 8000 or 5173 is still occupied. Unrelated processes were not terminated:"
    $remaining | Format-Table -AutoSize
    exit 1
}

if (-not $Quiet) {
    Write-Host "SmartAgriBrain Web and backend are stopped."
    Write-Host "Ports 5173 and 8000 are released; the backend camera owner is no longer running."
}
