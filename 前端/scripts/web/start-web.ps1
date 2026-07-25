$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
Set-Location -LiteralPath $projectRoot

$workspaceRoot = Split-Path (Split-Path $projectRoot -Parent) -Parent
$portableNode = Join-Path $workspaceRoot ".tools\node-v22.23.1-win-x64\node.exe"
$codexNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$viteCli = Join-Path $projectRoot "node_modules\vite\bin\vite.js"

if (-not (Test-Path -LiteralPath $viteCli)) {
  throw "Missing node_modules. Please run npm install first."
}

if (Test-Path -LiteralPath $portableNode) {
  Write-Host "Starting web server with project Node.js 22 LTS..."
  & $portableNode $viteCli --host 0.0.0.0 --port 5173
} elseif (Test-Path -LiteralPath $codexNode) {
  Write-Host "Starting web server with built-in Node..."
  & $codexNode $viteCli --host 0.0.0.0 --port 5173
} else {
  Write-Host "Built-in Node was not found. Falling back to system Node."
  Write-Host "If it still reports that Node is too old, install Node.js 22 LTS."
  npm run dev
}
