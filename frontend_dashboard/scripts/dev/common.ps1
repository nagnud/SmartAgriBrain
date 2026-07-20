$ErrorActionPreference = "Stop"

function Get-SmartAgriPaths {
    $proRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $webRoot = Split-Path $proRoot -Parent
    $workspaceRoot = Split-Path $webRoot -Parent

    $c5Manifest = Resolve-Path (Join-Path $webRoot "*\ESP32C5\main\idf_component.yml") -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty Path
    $s3Config = Resolve-Path (Join-Path $webRoot "*\*\study\platformio.ini") -ErrorAction SilentlyContinue |
        Where-Object { (Get-Content $_.Path -Raw) -match "esp32-s3-devkitc-1" } |
        Select-Object -First 1 -ExpandProperty Path
    $c5Root = if ($c5Manifest) { Split-Path (Split-Path $c5Manifest -Parent) -Parent } else { $null }
    $s3Root = if ($s3Config) { Split-Path $s3Config -Parent } else { $null }

    if (-not $c5Root) { throw "ESP32C5 project was not found below $webRoot" }

    [pscustomobject]@{
        ProRoot = $proRoot
        Frontend = $proRoot
        Backend = Join-Path $proRoot "backend_api"
        Workspace = $workspaceRoot
        C5 = $c5Root
        C5Ascii = "C:\SmartAgriBrain\ESP32C5-current-src"
        C5Build = "C:\SmartAgriBrain\build-c5-current"
        S3 = $s3Root
        Python = Join-Path $proRoot "backend_api\.venv\Scripts\python.exe"
        PlatformIO = Join-Path $proRoot "backend_api\.venv\Scripts\pio.exe"
        Node = Join-Path $workspaceRoot ".tools\node-v22.23.1-win-x64\node.exe"
        Npm = Join-Path $workspaceRoot ".tools\node-v22.23.1-win-x64\npm.cmd"
        IdfRoot = "C:\Espressif\frameworks\esp-idf-v5.5.2"
        IdfExport = "C:\Espressif\frameworks\esp-idf-v5.5.2\export.ps1"
    }
}

function Enter-EspIdf {
    param([Parameter(Mandatory = $true)] $Paths)
    if (-not (Test-Path $Paths.IdfExport)) {
        throw "ESP-IDF 5.5.2 is missing. Expected $($Paths.IdfExport)"
    }
    $env:IDF_TOOLS_PATH = "C:\Espressif\tools"
    $env:IDF_COMPONENT_CACHE_PATH = "C:\Espressif\component-cache"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:SENSAIR_C5_ASCII_ROOT = ($Paths.C5Ascii -replace "\\", "/")
    $pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
    if (Test-Path (Join-Path $pythonRoot "python.exe")) {
        $env:PATH = $pythonRoot + ";" + (Join-Path $pythonRoot "Scripts") + ";" + $env:PATH
    }
    # The new activate.py path is corrupted by Windows PowerShell 5 when the
    # user profile contains non-ASCII characters. The official legacy export
    # script performs the same environment setup without a temporary path.
    $legacyExport = Join-Path $Paths.IdfRoot "tools\legacy_exports\export_legacy.ps1"
    . "$legacyExport"
    # ccache 4.11 on this host cannot convert the Chinese workspace path.
    # Direct compiler invocations are slower but reliable.
    $env:IDF_CCACHE_ENABLE = "0"
}

function Assert-C5AsciiJunction {
    param([Parameter(Mandatory = $true)] $Paths)
    if (-not (Test-Path $Paths.C5Ascii)) {
        throw "C5 ASCII build source is missing. Expected $($Paths.C5Ascii)"
    }
}

function Sync-C5AsciiSource {
    param([Parameter(Mandatory = $true)] $Paths)

    $source = (Resolve-Path $Paths.C5).Path
    $mirror = $Paths.C5Ascii
    if ($mirror -ne "C:\SmartAgriBrain\ESP32C5-current-src") {
        throw "Refusing to sync C5 source to an unexpected mirror path: $mirror"
    }

    New-Item -ItemType Directory -Path $mirror -Force | Out-Null
    & robocopy $source $mirror /MIR /XD build .git /NFL /NDL /NJH /NJS /NC /NS
    $copyExitCode = $LASTEXITCODE
    if ($copyExitCode -gt 7) {
        throw "C5 ASCII source sync failed with robocopy exit code $copyExitCode"
    }

    $smartFarm = Join-Path $mirror "common_components\brookesia_app_smartfarm\esp_brookesia_app_smartfarm.cpp"
    if (-not (Test-Path $smartFarm)) {
        throw "C5 ASCII source sync is incomplete: $smartFarm is missing"
    }
}

function Enable-Node22 {
    param([Parameter(Mandatory = $true)] $Paths)
    if (-not (Test-Path $Paths.Node)) {
        throw "Node.js 22 LTS is missing. Expected $($Paths.Node)"
    }
    $env:PATH = (Split-Path $Paths.Node -Parent) + ";" + $env:PATH
}

function Resolve-S3Port {
    param(
        [string] $Port,
        [string] $C5Port = "COM5"
    )
    if ($Port) { return $Port.ToUpperInvariant() }

    $ports = Get-CimInstance Win32_PnPEntity |
        Where-Object {
            $_.Name -match "\(COM\d+\)" -and
            $_.PNPDeviceID -match "VID_(303A|10C4|1A86|0403)" -and
            $_.Name -notmatch "Bluetooth"
        } |
        ForEach-Object {
            [regex]::Match($_.Name, "COM\d+").Value.ToUpperInvariant()
        } |
        Where-Object { $_ -and $_ -ne $C5Port.ToUpperInvariant() } |
        Sort-Object -Unique

    if (@($ports).Count -eq 1) { return @($ports)[0] }
    if (@($ports).Count -eq 0) { throw "No ESP32-S3 serial port was detected. Connect it or pass -Port COMx." }
    throw "Multiple possible ESP32-S3 ports were detected: $($ports -join ', '). Pass -Port COMx."
}
