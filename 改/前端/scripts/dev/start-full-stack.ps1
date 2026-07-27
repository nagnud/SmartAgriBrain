[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths

# MQTT remains an external EMQX service. This launcher owns only the local Web
# and FastAPI processes.
$runtimeRoot = Join-Path $env:LOCALAPPDATA "SmartAgriBrain"
$logRoot = Join-Path $runtimeRoot "logs"
$statePath = Join-Path $runtimeRoot "full-stack.json"
$stopScript = Join-Path $PSScriptRoot "stop-full-stack.ps1"
$backendScript = Join-Path $paths.Frontend "scripts\backend\start-backend.ps1"
$frontendScript = Join-Path $paths.Frontend "scripts\web\start-web.ps1"

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

function Get-ListenerPid {
    param([int] $Port)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener) { return 0 }
    return [int]$listener.OwningProcess
}

function Stop-StaleBackendProcesses {
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -match "uvicorn\s+main:app" })) {
        Write-Host "Stopping stale backend uvicorn process (PID $($process.ProcessId))..."
        & taskkill.exe /PID "$($process.ProcessId)" /T /F 2>&1 | Out-Null
    }
}

function Wait-HttpReady {
    param(
        [string] $Url,
        [System.Diagnostics.Process] $LauncherProcess,
        [int] $TimeoutSeconds = 120
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($null -ne $LauncherProcess -and $LauncherProcess.HasExited) {
            return $false
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            # The process may not be listening yet or application startup may
            # still be running.
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Start-ManagedPowerShell {
    param(
        [Parameter(Mandatory = $true)][string] $ScriptPath,
        [string[]] $ScriptArguments = @(),
        [Parameter(Mandatory = $true)][string] $WorkingDirectory,
        [Parameter(Mandatory = $true)][string] $StandardOutputPath,
        [Parameter(Mandatory = $true)][string] $StandardErrorPath
    )

    # Windows PowerShell 5 Start-Process can fail when the inherited
    # environment contains case-colliding PATH/Path entries. ProcessStartInfo
    # avoids that implementation path. cmd.exe owns file redirection so native
    # stderr from pip/node is not converted into a terminating PowerShell error.
    foreach ($path in @($ScriptPath, $WorkingDirectory, $StandardOutputPath, $StandardErrorPath)) {
        if ($path.Contains('"')) {
            throw "Managed process path contains an unsupported quote: $path"
        }
    }

    $validatedArguments = @()
    foreach ($argument in $ScriptArguments) {
        if ($argument -notmatch "^-[A-Za-z][A-Za-z0-9-]*$") {
            throw "Unsafe managed script argument: $argument"
        }
        $validatedArguments += $argument
    }

    $powerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $scriptArgumentText = $validatedArguments -join " "
    $childCommand = '""{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}" {2} 1>"{3}" 2>"{4}""' -f `
        $powerShellExe, $ScriptPath, $scriptArgumentText, $StandardOutputPath, $StandardErrorPath

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $env:ComSpec
    $processInfo.Arguments = "/d /s /c $childCommand"
    $processInfo.WorkingDirectory = $WorkingDirectory
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    # The service itself is redirected by cmd.exe. Isolate cmd.exe's own
    # standard handles from the terminal that invoked this launcher.
    $processInfo.RedirectStandardInput = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    return [System.Diagnostics.Process]::Start($processInfo)
}

# A stale state file or an old managed listener must be cleaned before a new
# stack is launched. The stop script refuses to terminate unrelated listeners.
$hasState = Test-Path -LiteralPath $statePath
$hasManagedPort = $null -ne (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8000, 5173 } |
    Select-Object -First 1)
if ($hasState -or $hasManagedPort) {
    & $stopScript -Quiet
}
Stop-StaleBackendProcesses

$backendOut = Join-Path $logRoot "backend.out.log"
$backendErr = Join-Path $logRoot "backend.err.log"
$frontendOut = Join-Path $logRoot "frontend.out.log"
$frontendErr = Join-Path $logRoot "frontend.err.log"
foreach ($logPath in @($backendOut, $backendErr, $frontendOut, $frontendErr)) {
    Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
}

$backend = $null
$frontend = $null
try {
    # Managed background startup intentionally disables Uvicorn reload. Reload
    # replaces worker PIDs and was the main source of orphaned camera owners.
    $backend = Start-ManagedPowerShell `
        -ScriptPath $backendScript `
        -ScriptArguments @("-NoReload") `
        -WorkingDirectory $paths.Frontend `
        -StandardOutputPath $backendOut `
        -StandardErrorPath $backendErr

    @{
        backend_launcher_pid = $backend.Id
        frontend_launcher_pid = 0
        backend_listener_pid = 0
        frontend_listener_pid = 0
        started_at = (Get-Date).ToString("o")
        frontend_root = $paths.Frontend
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

    if (-not (Wait-HttpReady -Url "http://127.0.0.1:8000/api/v1/health" -LauncherProcess $backend)) {
        throw "Backend did not become ready. See $backendErr"
    }

    $frontend = Start-ManagedPowerShell `
        -ScriptPath $frontendScript `
        -WorkingDirectory $paths.Frontend `
        -StandardOutputPath $frontendOut `
        -StandardErrorPath $frontendErr

    if (-not (Wait-HttpReady -Url "http://127.0.0.1:5173" -LauncherProcess $frontend)) {
        throw "Web did not become ready. See $frontendErr"
    }

    $backendListenerPid = Get-ListenerPid -Port 8000
    $frontendListenerPid = Get-ListenerPid -Port 5173
    @{
        backend_launcher_pid = $backend.Id
        frontend_launcher_pid = $frontend.Id
        backend_listener_pid = $backendListenerPid
        frontend_listener_pid = $frontendListenerPid
        started_at = (Get-Date).ToString("o")
        frontend_root = $paths.Frontend
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

    Write-Host "Backend ready: http://127.0.0.1:8000 (PID $backendListenerPid)"
    Write-Host "Web ready:     http://127.0.0.1:5173 (PID $frontendListenerPid)"
    Write-Host "Logs: $logRoot"
    Write-Host "Stop: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\stop-full-stack.ps1"
} catch {
    Write-Warning $_.Exception.Message
    & $stopScript -Quiet
    throw
}
