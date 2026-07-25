param([string] $Port)
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths

if (-not $paths.Esp32) {
    throw "Regular ESP32 project is missing at repository-root\esp32."
}
if (-not $paths.PlatformIO) {
    throw "PlatformIO was not found in the backend virtual environment or user profile."
}

$resolvedPort = Resolve-Esp32Port -Port $Port
Push-Location $paths.Esp32
try { & $paths.PlatformIO device monitor --port $resolvedPort --baud 115200 }
finally { Pop-Location }
