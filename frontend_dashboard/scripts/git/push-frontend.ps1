param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $RemainingArguments
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$currentScript = [System.IO.Path]::GetFullPath($PSCommandPath)
$directory = [System.IO.DirectoryInfo]$PSScriptRoot

while ($directory) {
  $candidate = Join-Path $directory.FullName "scripts\git\push-frontend.ps1"
  if ((Test-Path -LiteralPath $candidate) -and ([System.IO.Path]::GetFullPath($candidate) -ne $currentScript)) {
    $candidateRootInfo = Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $candidate) "..\..") -ErrorAction SilentlyContinue
    if ($candidateRootInfo) {
      $candidateRoot = $candidateRootInfo.ProviderPath
      if ((Test-Path -LiteralPath (Join-Path $candidateRoot "package.json")) -and
          (Test-Path -LiteralPath (Join-Path $candidateRoot "src")) -and
          (Test-Path -LiteralPath (Join-Path $candidateRoot ".push-cache"))) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $candidate @RemainingArguments
        exit $LASTEXITCODE
      }
    }
  }
  $directory = $directory.Parent
}

throw "This is a generated forwarding script. Run the outer pro\scripts\git\push-frontend.bat instead."
