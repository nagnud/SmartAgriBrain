[CmdletBinding()]
param(
    [string]$BrokerAddress = "192.168.3.14",
    [string]$WifiSsid = "",
    [string]$WifiPassword = "",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WebRoot = Split-Path $ProjectRoot -Parent
$S3Config = Get-ChildItem -Path $WebRoot -Recurse -Filter "platformio.ini" -File |
    Where-Object { $_.FullName -notlike "$ProjectRoot*" } | Select-Object -First 1
$C5Marker = Get-ChildItem -Path $WebRoot -Recurse -Filter "sensair_iot.h" -File |
    Where-Object { $_.FullName -like "*common_components*sensair_iot*" } | Select-Object -First 1
if (!$S3Config -or !$C5Marker) { throw "Unable to locate the S3 or C5 project." }
$S3Root = $S3Config.Directory.FullName
$C5Root = (Resolve-Path (Join-Path $C5Marker.Directory.FullName "..\..\..")).Path
$RuntimeRoot = "D:\SmartAgriBrainRuntime\mosquitto"
$MosquittoRoot = "C:\Program Files\mosquitto"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $parent = Split-Path $Path -Parent
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function New-Password {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', 'A').Replace('/', 'B')
}

function Escape-CString([string]$Value) {
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

function Escape-Kconfig([string]$Value) {
    return Escape-CString $Value
}

function Read-KconfigString([string]$Content, [string]$Key) {
    $pattern = '(?m)^' + [regex]::Escape($Key) + '="(.*)"$'
    $match = [regex]::Match($Content, $pattern)
    if (!$match.Success) { return "" }
    return $match.Groups[1].Value.Replace('\"', '"').Replace('\\', '\')
}

function Set-KconfigString([string]$Content, [string]$Key, [string]$Value) {
    $line = $Key + '="' + (Escape-Kconfig $Value) + '"'
    $pattern = "(?m)^$([regex]::Escape($Key))=.*$"
    if ([regex]::IsMatch($Content, $pattern)) {
        return [regex]::Replace($Content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    }
    return $Content.TrimEnd() + "`r`n" + $line + "`r`n"
}

if (!(Test-Path (Join-Path $MosquittoRoot "mosquitto.exe"))) {
    throw "Mosquitto is not installed at $MosquittoRoot"
}

$C5Sdkconfig = Join-Path $C5Root "sdkconfig"
$ExistingC5Config = if (Test-Path $C5Sdkconfig) { [System.IO.File]::ReadAllText($C5Sdkconfig) } else { "" }
if (!$WifiSsid) { $WifiSsid = Read-KconfigString $ExistingC5Config "CONFIG_SENSAIR_WIFI_SSID" }
if (!$WifiPassword) { $WifiPassword = Read-KconfigString $ExistingC5Config "CONFIG_SENSAIR_WIFI_PASSWORD" }

$BackendPassword = New-Password
$S3Password = New-Password
$C5Password = New-Password

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
$PasswordFile = Join-Path $RuntimeRoot "passwd"
$AclFile = Join-Path $RuntimeRoot "acl"
$ConfigFile = Join-Path $RuntimeRoot "mosquitto.conf"
$MosquittoPasswd = Join-Path $MosquittoRoot "mosquitto_passwd.exe"

& $MosquittoPasswd -b -c $PasswordFile "sab_backend" $BackendPassword
& $MosquittoPasswd -b $PasswordFile "sab_s3" $S3Password
& $MosquittoPasswd -b $PasswordFile "sab_c5" $C5Password
if ($LASTEXITCODE -ne 0) { throw "mosquitto_passwd failed" }

$Acl = @"
user sab_backend
topic readwrite smartagribrain/v1/devices/#

user sab_s3
topic write smartagribrain/v1/devices/greenhouse_001_s3/telemetry
topic write smartagribrain/v1/devices/greenhouse_001_s3/status
topic write smartagribrain/v1/devices/greenhouse_001_s3/capabilities
topic write smartagribrain/v1/devices/greenhouse_001_s3/command_ack
topic read smartagribrain/v1/devices/greenhouse_001_s3/command

user sab_c5
topic write smartagribrain/v1/devices/greenhouse_001_c5/status
topic write smartagribrain/v1/devices/greenhouse_001_c5/capabilities
topic write smartagribrain/v1/devices/greenhouse_001_c5/assistant/request
topic write smartagribrain/v1/devices/greenhouse_001_c5/assistant/decision
topic read smartagribrain/v1/devices/greenhouse_001_c5/view_state
topic read smartagribrain/v1/devices/greenhouse_001_c5/assistant/response
"@
Write-Utf8NoBom $AclFile $Acl

$Config = @"
listener 1883 $BrokerAddress
listener_allow_anonymous false
password_file $($PasswordFile.Replace('\', '/'))
acl_file $($AclFile.Replace('\', '/'))
persistence true
persistence_location $($RuntimeRoot.Replace('\', '/'))/
autosave_interval 60
log_dest file $($RuntimeRoot.Replace('\', '/'))/mosquitto.log
log_type error
log_type warning
log_type notice
connection_messages true
"@
Write-Utf8NoBom $ConfigFile $Config

$BackendEnv = @"
DEFAULT_SITE_ID=greenhouse_001
S3_DEVICE_ID=greenhouse_001_s3
C5_DEVICE_ID=greenhouse_001_c5
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
MQTT_HOST=$BrokerAddress
MQTT_PORT=1883
MQTT_USERNAME=sab_backend
MQTT_PASSWORD=$BackendPassword
MQTT_TLS=false
MQTT_CLIENT_ID=smartagribrain-backend
MQTT_TOPIC_PREFIX=smartagribrain/v1
MQTT_QOS=1
MQTT_KEEPALIVE_SECONDS=60
MQTT_COMMAND_TTL_SECONDS=30
"@
Write-Utf8NoBom (Join-Path $ProjectRoot "backend_api\.env.mqtt.local") $BackendEnv

$FrontendEnv = @"
VITE_USE_MOCK=false
VITE_USE_MOCK_ASSISTANT=false
VITE_USE_MOCK_AI_ADVICE=false
VITE_USE_MOCK_KNOWLEDGE=false
VITE_USE_MOCK_WEATHER=false
VITE_API_BASE_URL=http://localhost:8000
VITE_SITE_ID=greenhouse_001
"@
Write-Utf8NoBom (Join-Path $ProjectRoot ".env.local") $FrontendEnv

$S3Secrets = @"
#pragma once
#define WIFI_SSID "$(Escape-CString $WifiSsid)"
#define WIFI_PASSWORD "$(Escape-CString $WifiPassword)"
#define MQTT_USER "sab_s3"
#define MQTT_PASSWORD "$(Escape-CString $S3Password)"
"@
Write-Utf8NoBom (Join-Path $S3Root "include\secrets.h") $S3Secrets

$C5Local = @"
CONFIG_SENSAIR_SITE_ID="greenhouse_001"
CONFIG_SENSAIR_DEVICE_ID="greenhouse_001_c5"
CONFIG_SENSAIR_S3_DEVICE_ID="greenhouse_001_s3"
CONFIG_SENSAIR_WIFI_SSID="$(Escape-Kconfig $WifiSsid)"
CONFIG_SENSAIR_WIFI_PASSWORD="$(Escape-Kconfig $WifiPassword)"
CONFIG_SENSAIR_MQTT_URI="mqtt://$($BrokerAddress):1883"
CONFIG_SENSAIR_MQTT_USERNAME="sab_c5"
CONFIG_SENSAIR_MQTT_PASSWORD="$(Escape-Kconfig $C5Password)"
"@
Write-Utf8NoBom (Join-Path $C5Root "sdkconfig.local") $C5Local

if ($ExistingC5Config) {
    $ExistingC5Config = Set-KconfigString $ExistingC5Config "CONFIG_SENSAIR_SITE_ID" "greenhouse_001"
    $ExistingC5Config = Set-KconfigString $ExistingC5Config "CONFIG_SENSAIR_DEVICE_ID" "greenhouse_001_c5"
    $ExistingC5Config = Set-KconfigString $ExistingC5Config "CONFIG_SENSAIR_S3_DEVICE_ID" "greenhouse_001_s3"
    $ExistingC5Config = Set-KconfigString $ExistingC5Config "CONFIG_SENSAIR_MQTT_URI" "mqtt://$($BrokerAddress):1883"
    $ExistingC5Config = Set-KconfigString $ExistingC5Config "CONFIG_SENSAIR_MQTT_USERNAME" "sab_c5"
    $ExistingC5Config = Set-KconfigString $ExistingC5Config "CONFIG_SENSAIR_MQTT_PASSWORD" $C5Password
    Write-Utf8NoBom $C5Sdkconfig $ExistingC5Config
}

if (!$NoStart) {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "mosquitto.exe" -and $_.CommandLine -like "*$ConfigFile*"
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    $Stdout = Join-Path $RuntimeRoot "broker.stdout.log"
    $Stderr = Join-Path $RuntimeRoot "broker.stderr.log"
    Start-Process -FilePath (Join-Path $MosquittoRoot "mosquitto.exe") `
        -ArgumentList @("-c", "`"$ConfigFile`"") -WindowStyle Hidden `
        -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
    Start-Sleep -Seconds 2
}

Write-Host "Local MQTT configuration completed."
Write-Host "Broker: $BrokerAddress`:1883"
Write-Host "Runtime: $RuntimeRoot"
Write-Host "Wi-Fi credentials present: $([bool]$WifiSsid)"
Write-Host "Passwords were written only to ignored local configuration files."
