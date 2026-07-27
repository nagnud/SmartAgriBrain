[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MqttUri,
    [Parameter(Mandatory = $true)]
    [string]$BackendUsername,
    [Parameter(Mandatory = $true)]
    [string]$BackendPassword,
    [Parameter(Mandatory = $true)]
    [string]$Esp32Username,
    [Parameter(Mandatory = $true)]
    [string]$Esp32Password,
    [string]$WifiSsid = "",
    [string]$WifiPassword = "",
    [string]$CaCertPath = "",
    [string]$C5Username = "",
    [string]$C5Password = "",
    [string]$C5BackendBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Escape-CString([string]$Value) {
    return $Value.Replace('\', '\\').Replace('"', '\"').Replace("`r", '').Replace("`n", '\n"' + "`r`n" + '    "')
}

function Escape-EnvValue([string]$Value) {
    if ($Value -match "[\r\n]") { throw "Environment values must not contain newlines." }
    return $Value
}

function Set-SdkconfigString([string]$Content, [string]$Name, [string]$Value) {
    if ($Value -match "[\r\n]") { throw "sdkconfig values must not contain newlines." }
    $escapedValue = $Value.Replace('\', '\\').Replace('"', '\"')
    $replacement = ("CONFIG_$Name=`"$escapedValue`"").Replace('$', '$$')
    $pattern = '(?m)^\s*CONFIG_' + [regex]::Escape($Name) + '=.*$'
    $configRegex = [regex]::new($pattern)
    if ($configRegex.IsMatch($Content)) {
        return $configRegex.Replace($Content, $replacement, 1)
    }
    if ($Content -and !$Content.EndsWith("`n")) { $Content += "`r`n" }
    return $Content + $replacement + "`r`n"
}

function Read-CDefine([string]$Content, [string]$Name) {
    $pattern = '(?m)^\s*#define\s+' + [regex]::Escape($Name) + '\s+"((?:\\.|[^"\\])*)"\s*(?://.*)?$'
    $match = [regex]::Match($Content, $pattern)
    if (!$match.Success) { return "" }
    return $match.Groups[1].Value.Replace('\"', '"').Replace('\\', '\')
}

function Set-CStringDefine([string]$Content, [string]$Name, [string]$Value) {
    $escapedValue = Escape-CString $Value
    $replacement = ("#define $Name `"$escapedValue`"").Replace('$', '$$')
    $pattern = '(?m)^\s*#define\s+' + [regex]::Escape($Name) + '\s+.*$'
    $defineRegex = [regex]::new($pattern)
    if ($defineRegex.IsMatch($Content)) {
        return $defineRegex.Replace($Content, $replacement, 1)
    }
    $endifRegex = [regex]::new('(?m)^#endif\s*$')
    return $endifRegex.Replace($Content, "$replacement`r`n`r`n#endif", 1)
}

function Set-CIntegerDefine([string]$Content, [string]$Name, [int]$Value) {
    $replacement = "#define $Name $Value"
    $pattern = '(?m)^\s*#define\s+' + [regex]::Escape($Name) + '\s+.*$'
    $defineRegex = [regex]::new($pattern)
    if ($defineRegex.IsMatch($Content)) {
        return $defineRegex.Replace($Content, $replacement, 1)
    }
    $endifRegex = [regex]::new('(?m)^#endif\s*$')
    return $endifRegex.Replace($Content, "$replacement`r`n`r`n#endif", 1)
}

try {
    $uri = [Uri]$MqttUri
} catch {
    throw "MqttUri must be the EMQX TLS endpoint mqtts://host:8883."
}
if ($uri.Scheme -ne "mqtts" -or !$uri.Host -or $uri.AbsolutePath -notin @("", "/")) {
    throw "MqttUri must contain only the mqtts scheme, host and optional port."
}
$uriPort = if ($uri.IsDefaultPort) { 8883 } else { $uri.Port }
if ($uriPort -ne 8883) {
    throw "MqttUri must use the EMQX TLS port 8883."
}
if ($C5BackendBaseUrl) {
    try {
        $c5BackendUri = [Uri]$C5BackendBaseUrl
    } catch {
        throw "C5BackendBaseUrl must be an http:// or https:// origin reachable from the C5."
    }
    if ($c5BackendUri.Scheme -notin @("http", "https") -or !$c5BackendUri.Host -or
            $c5BackendUri.AbsolutePath -notin @("", "/") -or $c5BackendUri.Query) {
        throw "C5BackendBaseUrl must contain only the http/https scheme, host and optional port."
    }
    $C5BackendBaseUrl = "$($c5BackendUri.Scheme)://$($c5BackendUri.Authority)"
}
if (!$CaCertPath) {
    throw "CaCertPath is required. Export the EMQX server CA certificate to a local PEM file first."
}
if ($CaCertPath -and !(Test-Path -LiteralPath $CaCertPath -PathType Leaf)) {
    throw "CA certificate was not found: $CaCertPath"
}

$frontendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$repositoryRoot = Split-Path $frontendRoot -Parent
$backendEnvPath = Join-Path $frontendRoot "backend_api\.env.mqtt.local"
$backendCaPath = Join-Path $env:LOCALAPPDATA "SmartAgriBrain\certs\emqx-ca.crt"
$esp32Include = Join-Path $repositoryRoot "esp32\include"
$esp32ConfigPath = Join-Path $esp32Include "config.h"
$esp32CaPath = Join-Path $esp32Include "emqx_ca_cert.h"
$c5Candidates = @(
    (Join-Path $repositoryRoot "esp32c5_voice_display"),
    (Join-Path $repositoryRoot "c5"),
    (Join-Path $repositoryRoot "改\c5")
)
$c5ProjectPath = $c5Candidates |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ "CMakeLists.txt") -PathType Leaf } |
    Select-Object -First 1

# MQTT deployment changes must not erase a working local Wi-Fi configuration.
# Explicit parameters still take precedence when the network itself is changing.
if (Test-Path -LiteralPath $esp32ConfigPath) {
    $existingEsp32Config = [System.IO.File]::ReadAllText($esp32ConfigPath)
    if (!$WifiSsid) { $WifiSsid = Read-CDefine $existingEsp32Config "WIFI_SSID" }
    if (!$WifiPassword) { $WifiPassword = Read-CDefine $existingEsp32Config "WIFI_PASSWORD" }
}
if (!$WifiSsid -or !$WifiPassword) {
    Write-Warning "ESP32 Wi-Fi credentials are empty. Supply -WifiSsid and -WifiPassword before flashing this configuration."
}

$port = 8883
if ($CaCertPath) {
    # dotenv files must be portable across PowerShell code pages. Keep the CA
    # copy under an ASCII local-app-data path so TLS setup never depends on a
    # workspace or desktop folder with localized characters.
    New-Item -ItemType Directory -Path (Split-Path -Parent $backendCaPath) -Force | Out-Null
    Copy-Item -LiteralPath $CaCertPath -Destination $backendCaPath -Force
}
$backendEnv = @"
# Generated by scripts/setup/configure-emqx.ps1. This ignored file contains local credentials.
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
MQTT_URI=$(Escape-EnvValue $MqttUri)
MQTT_TLS=true
MQTT_CA_CERT=$(if ($CaCertPath) { Escape-EnvValue $backendCaPath })
MQTT_TLS_INSECURE=false
MQTT_USERNAME=$(Escape-EnvValue $BackendUsername)
MQTT_PASSWORD=$(Escape-EnvValue $BackendPassword)
MQTT_CLIENT_ID=smartagribrain-api
MQTT_TOPIC_PREFIX=smartagribrain/v1
MQTT_QOS=1
MQTT_KEEPALIVE_SECONDS=60
MQTT_COMMAND_TTL_SECONDS=30
"@
Write-Utf8NoBom $backendEnvPath $backendEnv

$esp32Config = if (Test-Path -LiteralPath $esp32ConfigPath) {
    [System.IO.File]::ReadAllText($esp32ConfigPath)
} else {
@"
#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// This ignored file is the only local ESP32 deployment configuration.
// MQTT topics and the device ID are defined by include/iot_contract.h.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#define MQTT_SERVER ""
#define MQTT_PORT 8883
#define MQTT_USER ""
#define MQTT_PASS ""

#define LED_PIN 2
#define SEND_INTERVAL_MS 5000
#define BLINK_TIMES 3

#endif
"@
}
$esp32Config = Set-CStringDefine $esp32Config "WIFI_SSID" $WifiSsid
$esp32Config = Set-CStringDefine $esp32Config "WIFI_PASSWORD" $WifiPassword
$esp32Config = Set-CStringDefine $esp32Config "MQTT_SERVER" $uri.Host
$esp32Config = Set-CIntegerDefine $esp32Config "MQTT_PORT" $port
$esp32Config = Set-CStringDefine $esp32Config "MQTT_USER" $Esp32Username
$esp32Config = Set-CStringDefine $esp32Config "MQTT_PASS" $Esp32Password
Write-Utf8NoBom $esp32ConfigPath $esp32Config

if ($CaCertPath) {
    $pem = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $CaCertPath).Path)
    $esp32Ca = "#pragma once`r`n`r`n#define MQTT_ROOT_CA_CONFIGURED 1`r`nstatic const char MQTT_ROOT_CA_PEM[] = `"$(Escape-CString $pem)`";`r`n"
    Write-Utf8NoBom $esp32CaPath $esp32Ca
}

if ($C5Username -or $C5Password -or $C5BackendBaseUrl) {
    if (($C5Username -and !$C5Password) -or ($C5Password -and !$C5Username)) {
        throw "Provide both C5Username and C5Password, or omit both."
    }
    if (!$c5ProjectPath) {
        throw "C5 credentials were supplied, but no C5 ESP-IDF project was found."
    }
    $c5ConfigPath = Join-Path $c5ProjectPath "sdkconfig.local"
    $c5Config = if (Test-Path -LiteralPath $c5ConfigPath) {
        [System.IO.File]::ReadAllText($c5ConfigPath)
    } else {
        ""
    }
    $c5Config = Set-SdkconfigString $c5Config "SENSAIR_SITE_ID" "greenhouse_001"
    $c5Config = Set-SdkconfigString $c5Config "SENSAIR_DEVICE_ID" "greenhouse_001_c5"
    $c5Config = Set-SdkconfigString $c5Config "SENSAIR_S3_DEVICE_ID" "greenhouse_001_s3"
    $c5Config = Set-SdkconfigString $c5Config "SENSAIR_MQTT_URI" $MqttUri
    $c5Config = Set-SdkconfigString $c5Config "SENSAIR_MQTT_TOPIC_PREFIX" "smartagribrain/v1"
    if ($C5Username) {
        $c5Config = Set-SdkconfigString $c5Config "SENSAIR_MQTT_USERNAME" $C5Username
        $c5Config = Set-SdkconfigString $c5Config "SENSAIR_MQTT_PASSWORD" $C5Password
    }
    if ($C5BackendBaseUrl) {
        $voiceWsScheme = if ($c5BackendUri.Scheme -eq "https") { "wss" } else { "ws" }
        $c5Config = Set-SdkconfigString $c5Config "SENSAIR_VOICE_API_URL" "$C5BackendBaseUrl/api/v1/assistant/voice?site_id=greenhouse_001"
        $c5Config = Set-SdkconfigString $c5Config "SENSAIR_VOICE_LIVE_WS_URL" "${voiceWsScheme}://$($c5BackendUri.Authority)/api/v1/assistant/voice/live"
    }
    if ($WifiSsid) { $c5Config = Set-SdkconfigString $c5Config "SENSAIR_WIFI_SSID" $WifiSsid }
    if ($WifiPassword) { $c5Config = Set-SdkconfigString $c5Config "SENSAIR_WIFI_PASSWORD" $WifiPassword }
    Write-Utf8NoBom $c5ConfigPath $c5Config
    Write-Host "C5 EMQX configuration: $c5ConfigPath"
}

Write-Host "EMQX configuration was written to ignored local files."
Write-Host "Endpoint: $($uri.Scheme)://$($uri.Host):$port"
Write-Host "No local Mosquitto process or configuration was created."
