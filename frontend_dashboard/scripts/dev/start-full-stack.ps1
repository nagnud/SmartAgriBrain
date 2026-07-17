. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths

if (-not (Test-NetConnection -ComputerName "192.168.3.14" -Port 1883 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    & (Join-Path $paths.ProRoot "scripts\setup\setup-local-mqtt.ps1")
}

$logRoot = Join-Path $env:LOCALAPPDATA "SmartAgriBrain\logs"
New-Item -ItemType Directory -Force $logRoot | Out-Null

$backendScript = Join-Path $paths.ProRoot "scripts\backend\start-backend.ps1"
$frontendScript = Join-Path $paths.ProRoot "scripts\web\start-web.ps1"
$backend = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendScript
) -RedirectStandardOutput (Join-Path $logRoot "backend.out.log") -RedirectStandardError (Join-Path $logRoot "backend.err.log")
$frontend = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $frontendScript
) -RedirectStandardOutput (Join-Path $logRoot "frontend.out.log") -RedirectStandardError (Join-Path $logRoot "frontend.err.log")

Start-Sleep -Seconds 2
Write-Host "Backend PID: $($backend.Id)  http://127.0.0.1:8000"
Write-Host "Frontend PID: $($frontend.Id)  http://127.0.0.1:5173"
Write-Host "Logs: $logRoot"
