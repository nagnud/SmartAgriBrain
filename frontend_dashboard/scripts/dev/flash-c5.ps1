param([string] $Port = "COM5")
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
Sync-C5AsciiSource $paths
Assert-C5AsciiJunction $paths
Enter-EspIdf $paths
Push-Location $paths.C5Ascii
try {
    idf.py -B $paths.C5Build reconfigure
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    idf.py -B $paths.C5Build build
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    idf.py -B $paths.C5Build -p $Port flash
    exit $LASTEXITCODE
}
finally { Pop-Location }
