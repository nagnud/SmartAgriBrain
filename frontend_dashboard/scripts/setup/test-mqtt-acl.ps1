[CmdletBinding()]
param([string]$BrokerAddress = "192.168.3.14")

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WebRoot = Split-Path $ProjectRoot -Parent
$MosquittoRoot = "C:\Program Files\mosquitto"
$RuntimeRoot = "D:\SmartAgriBrainRuntime\mosquitto"

function Read-Match([string]$Path, [string]$Pattern) {
    $match = [regex]::Match([IO.File]::ReadAllText($Path), $Pattern, [Text.RegularExpressions.RegexOptions]::Multiline)
    if (!$match.Success) { throw "Missing local credential in $Path" }
    return $match.Groups[1].Value.Trim()
}

$S3Config = Get-ChildItem -Path $WebRoot -Recurse -Filter "secrets.h" -File |
    Where-Object { $_.FullName -like "*esp32s3*study*include*" } | Select-Object -First 1
$C5Config = Get-ChildItem -Path $WebRoot -Recurse -Filter "sdkconfig.local" -File |
    Where-Object { $_.FullName -like "*ESP32C5*" } | Select-Object -First 1
if (!$S3Config -or !$C5Config) { throw "Run setup-local-mqtt.ps1 first." }

$BackendPassword = Read-Match (Join-Path $ProjectRoot "backend_api\.env.mqtt.local") '^MQTT_PASSWORD=(.+)$'
$S3Password = Read-Match $S3Config.FullName '^#define MQTT_PASSWORD "(.+)"$'
$C5Password = Read-Match $C5Config.FullName '^CONFIG_SENSAIR_MQTT_PASSWORD="(.+)"$'
$Sub = Join-Path $MosquittoRoot "mosquitto_sub.exe"
$Pub = Join-Path $MosquittoRoot "mosquitto_pub.exe"
$Nonce = [guid]::NewGuid().ToString("N")

function Run-Probe(
    [string]$User,
    [string]$Password,
    [string]$Topic,
    [string]$PublishTopic,
    [string]$Expected,
    [bool]$ShouldReceive
) {
    $publisher = Start-Job -ScriptBlock {
        param($PubExe, $HostName, $Secret, $TargetTopic, $Message)
        Start-Sleep -Seconds 1
        & $PubExe -h $HostName -p 1883 -u "sab_backend" -P $Secret -t $TargetTopic -q 1 -m $Message
    } -ArgumentList $Pub, $BrokerAddress, $BackendPassword, $PublishTopic, $Expected
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $received = ((& $Sub -h $BrokerAddress -p 1883 -u $User -P $Password -t $Topic -q 1 -C 1 -W 3 2>$null) | Out-String).Trim()
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    $null = Wait-Job $publisher -Timeout 5
    Receive-Job $publisher -ErrorAction SilentlyContinue | Out-Null
    Stop-Job $publisher -ErrorAction SilentlyContinue
    Remove-Job $publisher -Force -ErrorAction SilentlyContinue
    if ($ShouldReceive -and $received -ne $Expected) {
        throw "$User did not receive its authorized topic."
    }
    if (!$ShouldReceive -and $received) {
        throw "$User received a forbidden topic."
    }
}

$C5Response = "smartagribrain/v1/devices/greenhouse_001_c5/assistant/response"
$S3Command = "smartagribrain/v1/devices/greenhouse_001_s3/command"
$S3Telemetry = "smartagribrain/v1/devices/greenhouse_001_s3/telemetry"

Run-Probe "sab_c5" $C5Password $C5Response $C5Response "c5-own-$Nonce" $true
Run-Probe "sab_s3" $S3Password $S3Command $S3Command "s3-own-$Nonce" $true
Run-Probe "sab_s3" $S3Password $C5Response $C5Response "s3-forbidden-$Nonce" $false
Run-Probe "sab_c5" $C5Password $S3Telemetry $S3Telemetry "c5-forbidden-$Nonce" $false

Write-Host "MQTT ACL verified: backend relay access works; C5 and S3 cannot read each other's topics."
