$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
$repoUrl = "https://github.com/nagnud/SmartAgriBrain.git"
$branchName = "feature/frontend"
$tempRoot = Join-Path $projectRoot ".push-tmp"
$repoDir = Join-Path $tempRoot "SmartAgriBrain"
$targetDir = Join-Path $repoDir "frontend_dashboard"

function Invoke-GitChecked {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Arguments
  )

  & git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

Set-Location -LiteralPath $projectRoot

if (Test-Path -LiteralPath $tempRoot) {
  Write-Host "Removing old temporary checkout..."
  Remove-Item -LiteralPath $tempRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

Write-Host "Cloning repository branch $branchName..."
Invoke-GitChecked @("-c", "http.version=HTTP/1.1", "clone", "--branch", $branchName, $repoUrl, $repoDir)

Write-Host "Copying current pro project to frontend_dashboard..."
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
robocopy $projectRoot $targetDir /MIR /XD node_modules dist .push-tmp /XF dev-server.log tsconfig.tsbuildinfo /NFL /NDL /NJH /NJS /NC /NS
if ($LASTEXITCODE -gt 7) {
  throw "robocopy failed with exit code $LASTEXITCODE"
}

Set-Location -LiteralPath $repoDir
Invoke-GitChecked @("add", "frontend_dashboard")

$changes = & git status --porcelain
if (-not $changes) {
  Write-Host "No changes to commit."
} else {
  Invoke-GitChecked @("commit", "-m", "feat: add frontend page")
}

Invoke-GitChecked @("push", "origin", $branchName)
Write-Host "Done. Frontend dashboard has been pushed."
