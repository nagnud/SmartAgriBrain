. (Join-Path $PSScriptRoot "common.ps1")
$paths = Get-SmartAgriPaths

$checks = @(
    @{ Name = "Node.js 22"; Path = $paths.Node },
    @{ Name = "npm"; Path = $paths.Npm },
    @{ Name = "Backend Python"; Path = $paths.Python },
    @{ Name = "PlatformIO"; Path = $paths.PlatformIO },
    @{ Name = "ESP-IDF 5.5.2"; Path = $paths.IdfExport },
    @{ Name = "C5 ASCII build junction"; Path = $paths.C5Ascii },
    @{ Name = "Mosquitto client"; Path = "C:\Program Files\mosquitto\mosquitto_pub.exe" },
    @{ Name = "Backend MQTT config"; Path = (Join-Path $paths.Backend ".env.mqtt.local") },
    @{ Name = "S3 secrets"; Path = (Join-Path $paths.S3 "include\secrets.h") },
    @{ Name = "C5 local config"; Path = (Join-Path $paths.C5 "sdkconfig.local") }
)

$failed = $false
foreach ($check in $checks) {
    $ok = Test-Path $check.Path
    if (-not $ok) { $failed = $true }
    [pscustomobject]@{ Check = $check.Name; Status = if ($ok) { "OK" } else { "MISSING" }; Path = $check.Path }
}

$broker = Test-NetConnection -ComputerName "192.168.3.14" -Port 1883 -InformationLevel Quiet -WarningAction SilentlyContinue
[pscustomobject]@{ Check = "MQTT 192.168.3.14:1883"; Status = if ($broker) { "OK" } else { "UNREACHABLE" }; Path = "local private LAN" }
if (-not $broker) { $failed = $true }

if (Test-Path $paths.Node) { & $paths.Node --version }
if (Test-Path $paths.PlatformIO) { & $paths.PlatformIO --version }
if ($failed) { exit 1 }
