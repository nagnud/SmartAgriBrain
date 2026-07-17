param([string] $Port)
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
$resolvedPort = Resolve-S3Port -Port $Port
Push-Location $paths.S3
try { & $paths.PlatformIO run --target upload --upload-port $resolvedPort; exit $LASTEXITCODE }
finally { Pop-Location }
