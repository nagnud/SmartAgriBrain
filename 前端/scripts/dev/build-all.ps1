param(
    [switch] $SkipEsp32,
    [switch] $SkipC5
)
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
Enable-NodeRuntime $paths

Push-Location $paths.Backend
try { & $paths.Python -m pytest -q; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
finally { Pop-Location }

Push-Location $paths.Frontend
try { & $paths.Npm run build; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
finally { Pop-Location }

if (-not $SkipEsp32) {
    if (-not $paths.Esp32) { throw "Regular ESP32 project is missing at repository-root\esp32." }
    if (-not $paths.PlatformIO) { throw "PlatformIO was not found in the backend virtual environment or user profile." }
    Push-Location $paths.Esp32
    try { & $paths.PlatformIO run; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
    finally { Pop-Location }
}

if (-not $SkipC5 -and $paths.C5) {
    Sync-C5AsciiSource $paths
    Assert-C5AsciiJunction $paths
    Enter-EspIdf $paths
    Push-Location $paths.C5Ascii
    try {
        idf.py -B $paths.C5Build reconfigure; if ($LASTEXITCODE) { exit $LASTEXITCODE }
        idf.py -B $paths.C5Build build; if ($LASTEXITCODE) { exit $LASTEXITCODE }
    }
    finally { Pop-Location }
} elseif (-not $SkipC5) {
    Write-Warning "ESP32-C5 source is not present on this branch; skipping the C5 build."
}
