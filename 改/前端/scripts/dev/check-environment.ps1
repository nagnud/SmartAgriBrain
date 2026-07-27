. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths

$requiredChecks = @(
    @{ Name = "Node.js >=20.19"; Path = $paths.Node },
    @{ Name = "npm"; Path = $paths.Npm },
    @{ Name = "Backend Python"; Path = $paths.Python }
)
$optionalChecks = @(
    @{ Name = "Regular ESP32 project"; Path = $paths.Esp32 },
    @{ Name = "PlatformIO"; Path = $paths.PlatformIO },
    @{ Name = "Backend MQTT config"; Path = (Join-Path $paths.Backend ".env.mqtt.local") },
    @{ Name = "ESP32 local config"; Path = if ($paths.Esp32) { Join-Path $paths.Esp32 "include\config.h" } else { $null } },
    @{ Name = "ESP32-C5 source"; Path = $paths.C5 },
    @{ Name = "ESP-IDF 5.5.2"; Path = $paths.IdfExport },
    @{ Name = "C5 ASCII build mirror"; Path = $paths.C5Ascii },
    @{ Name = "C5 local config"; Path = if ($paths.C5) { Join-Path $paths.C5 "sdkconfig.local" } else { $null } }
)

$failed = $false
foreach ($check in $requiredChecks) {
    $ok = -not [string]::IsNullOrWhiteSpace([string]$check.Path) -and (Test-Path -LiteralPath $check.Path)
    if (-not $ok) { $failed = $true }
    [pscustomobject]@{ Check = $check.Name; Status = if ($ok) { "OK" } else { "MISSING" }; Required = $true; Path = $check.Path }
}
foreach ($check in $optionalChecks) {
    $ok = -not [string]::IsNullOrWhiteSpace([string]$check.Path) -and (Test-Path -LiteralPath $check.Path)
    [pscustomobject]@{ Check = $check.Name; Status = if ($ok) { "OK" } else { "NOT CONFIGURED" }; Required = $false; Path = $check.Path }
}

$mqttConfigPath = Join-Path $paths.Backend ".env.mqtt.local"
if (Test-Path -LiteralPath $mqttConfigPath) {
    $mqttUriLine = Get-Content -LiteralPath $mqttConfigPath | Where-Object { $_ -match '^MQTT_URI=' } | Select-Object -First 1
    $mqttUri = if ($mqttUriLine) { ($mqttUriLine -split '=', 2)[1].Trim() } else { '' }
    try {
        $endpoint = [Uri]$mqttUri
        if ($endpoint.Scheme -notin @('mqtt', 'mqtts') -or !$endpoint.Host) { throw 'invalid MQTT_URI' }
        $port = if ($endpoint.IsDefaultPort) { if ($endpoint.Scheme -eq 'mqtts') { 8883 } else { 1883 } } else { $endpoint.Port }
        $reachable = Test-NetConnection -ComputerName $endpoint.Host -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
        [pscustomobject]@{ Check = "EMQX $($endpoint.Host):$port"; Status = if ($reachable) { "OK" } else { "UNREACHABLE" }; Required = $false; Path = $mqttUri }
    } catch {
        [pscustomobject]@{ Check = "EMQX MQTT_URI"; Status = "INVALID"; Required = $false; Path = $mqttUri }
    }
} else {
    [pscustomobject]@{ Check = "EMQX MQTT config"; Status = "NOT CONFIGURED"; Required = $false; Path = $mqttConfigPath }
}

if (Test-Path $paths.Node) { & $paths.Node --version }
if (Test-Path $paths.PlatformIO) { & $paths.PlatformIO --version }
if ($failed) { exit 1 }
