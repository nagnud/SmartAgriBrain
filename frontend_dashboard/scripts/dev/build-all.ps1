param([switch] $SkipC5)
. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths
Enable-Node22 $paths

Push-Location $paths.Backend
try { & $paths.Python -m unittest discover -s tests -v; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
finally { Pop-Location }

Push-Location $paths.Frontend
try { & $paths.Npm run build; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
finally { Pop-Location }

Push-Location $paths.S3
try { & $paths.PlatformIO run; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
finally { Pop-Location }

if (-not $SkipC5) {
    Sync-C5AsciiSource $paths
    Assert-C5AsciiJunction $paths
    Enter-EspIdf $paths
    Push-Location $paths.C5Ascii
    try {
        idf.py -B $paths.C5Build reconfigure; if ($LASTEXITCODE) { exit $LASTEXITCODE }
        idf.py -B $paths.C5Build build; if ($LASTEXITCODE) { exit $LASTEXITCODE }
    }
    finally { Pop-Location }
}
