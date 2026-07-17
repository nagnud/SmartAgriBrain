param([string] $Port = "COM5")
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
Assert-C5AsciiJunction $paths
Enter-EspIdf $paths
Push-Location $paths.C5Ascii
try { idf.py -B $paths.C5Build -p $Port flash; exit $LASTEXITCODE }
finally { Pop-Location }
