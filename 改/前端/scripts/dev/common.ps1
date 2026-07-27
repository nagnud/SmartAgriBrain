$ErrorActionPreference = "Stop"

function Get-SmartAgriPaths {
    $frontendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $repositoryRoot = Split-Path $frontendRoot -Parent
    $workspaceRoot = Split-Path $repositoryRoot -Parent

    # The current control board is the regular ESP32 PlatformIO project at
    # repository-root/esp32. The old S3 discovery pattern pointed at a removed
    # historical checkout and made every development command fail up front.
    $esp32Candidate = Join-Path $repositoryRoot "esp32"
    $esp32Root = if (Test-Path (Join-Path $esp32Candidate "platformio.ini")) {
        (Resolve-Path $esp32Candidate).Path
    } else {
        $null
    }

    # The C5 source is optional on branches that only contain Web/backend and
    # regular ESP32 code. C5-specific commands validate it when invoked.
    $c5Candidate = Join-Path $repositoryRoot "esp32c5_voice_display"
    $c5Root = if (Test-Path (Join-Path $c5Candidate "main\idf_component.yml")) {
        (Resolve-Path $c5Candidate).Path
    } else {
        $null
    }

    $portableNodeRoot = Join-Path $workspaceRoot ".tools\node-v22.23.1-win-x64"
    $systemNode = Get-Command node.exe -ErrorAction SilentlyContinue
    $systemNpm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    $backendVenv = Join-Path $frontendRoot "backend_api\.venv"
    $userPlatformIO = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\pio.exe"

    [pscustomobject]@{
        Frontend = $frontendRoot
        Backend = Join-Path $frontendRoot "backend_api"
        Repository = $repositoryRoot
        Workspace = $workspaceRoot
        Esp32 = $esp32Root
        C5 = $c5Root
        C5Ascii = "C:\SmartAgriBrain\ESP32C5-current-src"
        C5Build = "C:\SmartAgriBrain\build-c5-current"
        Python = Join-Path $backendVenv "Scripts\python.exe"
        PlatformIO = if (Test-Path (Join-Path $backendVenv "Scripts\pio.exe")) {
            Join-Path $backendVenv "Scripts\pio.exe"
        } elseif (Test-Path $userPlatformIO) {
            $userPlatformIO
        } else {
            $null
        }
        Node = if (Test-Path (Join-Path $portableNodeRoot "node.exe")) {
            Join-Path $portableNodeRoot "node.exe"
        } elseif ($systemNode) {
            $systemNode.Source
        } else {
            $null
        }
        Npm = if (Test-Path (Join-Path $portableNodeRoot "npm.cmd")) {
            Join-Path $portableNodeRoot "npm.cmd"
        } elseif ($systemNpm) {
            $systemNpm.Source
        } else {
            $null
        }
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
    if (-not $Paths.C5) {
        throw "ESP32-C5 source is missing. Expected repository-root\esp32c5_voice_display."
    }
    if (-not (Test-Path $Paths.C5Ascii)) {
        throw "C5 ASCII build source is missing. Expected $($Paths.C5Ascii)"
    }
}

function Sync-C5AsciiSource {
    param([Parameter(Mandatory = $true)] $Paths)

    if (-not $Paths.C5) {
        throw "ESP32-C5 source is missing. Expected repository-root\esp32c5_voice_display."
    }

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

function Enable-NodeRuntime {
    param([Parameter(Mandatory = $true)] $Paths)
    if (-not (Test-Path $Paths.Node)) {
        throw "Node.js >=20.19 is missing."
    }
    $env:PATH = (Split-Path $Paths.Node -Parent) + ";" + $env:PATH
}

function Resolve-Esp32Port {
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
    if (@($ports).Count -eq 0) { throw "No regular ESP32 serial port was detected. Connect it or pass -Port COMx." }
    throw "Multiple possible regular ESP32 ports were detected: $($ports -join ', '). Pass -Port COMx."
}
