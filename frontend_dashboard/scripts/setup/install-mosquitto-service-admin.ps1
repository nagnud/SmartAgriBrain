[CmdletBinding()]
param(
    [string]$BrokerAddress = "192.168.3.14",
    [string]$AllowedSubnet = "192.168.3.0/24"
)

$ErrorActionPreference = "Stop"
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (!$IsAdmin) { throw "Run this script from an elevated PowerShell window." }

$Source = "D:\SmartAgriBrainRuntime\mosquitto"
$Install = "C:\ProgramData\SmartAgriBrain\mosquitto"
$MosquittoExe = "C:\Program Files\mosquitto\mosquitto.exe"
if (!(Test-Path (Join-Path $Source "mosquitto.conf"))) { throw "Run setup-local-mqtt.ps1 first." }

New-Item -ItemType Directory -Force -Path $Install | Out-Null
Copy-Item (Join-Path $Source "passwd") (Join-Path $Install "passwd") -Force
Copy-Item (Join-Path $Source "acl") (Join-Path $Install "acl") -Force
$Config = Get-Content -Raw (Join-Path $Source "mosquitto.conf")
$Config = $Config.Replace($Source.Replace('\', '/'), $Install.Replace('\', '/'))
[IO.File]::WriteAllText((Join-Path $Install "mosquitto.conf"), $Config, (New-Object Text.UTF8Encoding($false)))

Stop-Service mosquitto -Force
$BinPath = '"{0}" -c "{1}" run' -f $MosquittoExe, (Join-Path $Install "mosquitto.conf")
& sc.exe config mosquitto binPath= $BinPath start= auto | Out-Null

Get-NetFirewallRule -DisplayName "SmartAgriBrain MQTT private LAN" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "SmartAgriBrain MQTT private LAN" -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 1883 -LocalAddress $BrokerAddress -RemoteAddress $AllowedSubnet -Profile Private | Out-Null
Start-Service mosquitto
Write-Host "Secure Mosquitto service and private-subnet firewall rule are active."

