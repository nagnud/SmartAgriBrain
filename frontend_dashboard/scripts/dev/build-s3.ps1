. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
Push-Location $paths.S3
try { & $paths.PlatformIO run; exit $LASTEXITCODE }
finally { Pop-Location }
