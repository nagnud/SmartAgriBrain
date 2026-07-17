[CmdletBinding()]
param(
    [string]$WifiSsid = "",
    [string]$WifiPassword = ""
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Escape-Kconfig([string]$Value) {
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

function Set-KconfigString([string]$Content, [string]$Key, [string]$Value) {
    $line = $Key + '="' + (Escape-Kconfig $Value) + '"'
    $pattern = '(?m)^' + [regex]::Escape($Key) + '=.*$'
    if ([regex]::IsMatch($Content, $pattern)) {
        return [regex]::Replace($Content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    }
    return $Content.TrimEnd() + "`r`n" + $line + "`r`n"
}

function Set-CDefine([string]$Content, [string]$Key, [string]$Value) {
    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    $line = '#define ' + $Key + ' "' + $escaped + '"'
    $pattern = '(?m)^\s*#define\s+' + [regex]::Escape($Key) + '\s+.*$'
    if ([regex]::IsMatch($Content, $pattern)) {
        return [regex]::Replace($Content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    }
    return $Content.TrimEnd() + "`r`n" + $line + "`r`n"
}

if (!$WifiSsid) {
    $interfaces = netsh wlan show interfaces
    $ssidLine = $interfaces | Where-Object {
        $_ -match '^\s*SSID\s*:' -and $_ -notmatch 'BSSID'
    } | Select-Object -First 1
    if (!$ssidLine) { throw "No connected Wi-Fi interface was found." }
    $WifiSsid = ($ssidLine -split ':', 2)[1].Trim()
}

if (!$WifiPassword) {
    $profile = netsh wlan show profile name="$WifiSsid" key=clear
    $keyLine = $profile | Where-Object {
        $_ -match '^\s*(Key Content|关键内容)\s*:'
    } | Select-Object -First 1
    if (!$keyLine) { throw "The saved Wi-Fi password could not be read. Run this script from an elevated terminal or provide it explicitly." }
    $WifiPassword = ($keyLine -split ':', 2)[1].Trim()
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WebRoot = Split-Path $ProjectRoot -Parent
$C5Marker = Get-ChildItem -Path $WebRoot -Recurse -Filter "sensair_iot.h" -File |
    Where-Object { $_.FullName -like "*common_components*sensair_iot*" } | Select-Object -First 1
$Esp32Project = Get-ChildItem -Path $WebRoot -Recurse -Filter "platformio.ini" -File |
    Where-Object { $_.FullName -notlike "$ProjectRoot*" } | Select-Object -First 1
if (!$C5Marker -or !$Esp32Project) { throw "Unable to locate both edge-device projects." }

$C5Root = (Resolve-Path (Join-Path $C5Marker.Directory.FullName "..\..\..")).Path
foreach ($name in @("sdkconfig.local", "sdkconfig")) {
    $path = Join-Path $C5Root $name
    if (!(Test-Path $path)) { continue }
    $content = [System.IO.File]::ReadAllText($path)
    $content = Set-KconfigString $content "CONFIG_SENSAIR_WIFI_SSID" $WifiSsid
    $content = Set-KconfigString $content "CONFIG_SENSAIR_WIFI_PASSWORD" $WifiPassword
    Write-Utf8NoBom $path $content
}

$SecretsPath = Join-Path $Esp32Project.Directory.FullName "include\secrets.h"
if (Test-Path $SecretsPath) {
    $secrets = [System.IO.File]::ReadAllText($SecretsPath)
    $secrets = Set-CDefine $secrets "WIFI_SSID" $WifiSsid
    $secrets = Set-CDefine $secrets "WIFI_PASSWORD" $WifiPassword
    Write-Utf8NoBom $SecretsPath $secrets
}

Write-Host "Edge-device Wi-Fi configuration updated for: $WifiSsid"
Write-Host "The password was written only to ignored local files and was not printed."
