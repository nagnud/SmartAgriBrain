param(
    [switch] $FullClean,
    [switch] $Reconfigure
)
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
Sync-C5AsciiSource $paths
Assert-C5AsciiJunction $paths
Enter-EspIdf $paths
Push-Location $paths.C5Ascii
try {
    if ($FullClean) {
        idf.py -B $paths.C5Build fullclean
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
    }
    idf.py -B $paths.C5Build reconfigure
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    idf.py -B $paths.C5Build build
    exit $LASTEXITCODE
}
finally { Pop-Location }
