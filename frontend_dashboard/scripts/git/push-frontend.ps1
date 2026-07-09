param(
  [string] $Message
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
$repoUrl = "https://github.com/nagnud/SmartAgriBrain.git"
$branchName = "feature/frontend"
$tempRoot = Join-Path $projectRoot ".push-tmp"
$repoDir = Join-Path $tempRoot "SmartAgriBrain"
$targetDir = Join-Path $repoDir "frontend_dashboard"
$credentialFileName = "push$([char]0x8F93)$([char]0x5165).md"
$credentialPath = Join-Path $PSScriptRoot $credentialFileName
$askPassRoot = $null
$askPassScript = $null
$askPassCommand = $null
$networkGitAttempts = 3
$networkGitRetryDelaySeconds = 5

function Invoke-GitCaptured {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Arguments
  )

  $previousErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $output = & git @Arguments 2>&1 | ForEach-Object { $_.ToString() }
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  [pscustomobject]@{
    ExitCode = $exitCode
    Output = @($output)
  }
}

function Test-TransientGitNetworkError {
  param(
    [string] $Message
  )

  return $Message -match "Recv failure|Connection was reset|Connection reset|Failed to connect|Couldn't connect|timed out|Could not resolve host|curl 28|curl 35|curl 56|HTTP/2 stream|SSL_read|SSL_ERROR_SYSCALL"
}

function Invoke-GitChecked {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Arguments,

    [int] $Attempts = 1,

    [switch] $NoThrow
  )

  $lastResult = $null
  for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    $lastResult = Invoke-GitCaptured -Arguments $Arguments
    $message = ($lastResult.Output | Out-String).Trim()

    if ($lastResult.ExitCode -eq 0) {
      if ($message -and -not $NoThrow) {
        Write-Host $message
      }
      if ($NoThrow) {
        return $lastResult
      }

      return
    }

    if ($attempt -lt $Attempts -and (Test-TransientGitNetworkError -Message $message)) {
      Write-Warning ("Git network error, retrying in {0}s ({1}/{2})..." -f $networkGitRetryDelaySeconds, $attempt, $Attempts)
      if ($message) {
        Write-Host $message
      }
      Start-Sleep -Seconds $networkGitRetryDelaySeconds
      continue
    }

    if ($NoThrow) {
      return $lastResult
    }

    if ($message) {
      throw "git $($Arguments -join ' ') failed with exit code $($lastResult.ExitCode).`n$message"
    }

    throw "git $($Arguments -join ' ') failed with exit code $($lastResult.ExitCode)."
  }
}

function Get-PushCredentials {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Path
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Credential file not found: $Path"
  }

  $text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($Path))
  $tokenMatch = [regex]::Match($text, "(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)")
  if (-not $tokenMatch.Success) {
    throw "Could not find a GitHub token in $Path."
  }

  $fullWidthColon = [string][char]0xFF1A
  $username = $null
  foreach ($line in ($text -split "`r?`n")) {
    if ($line -match "(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)") {
      continue
    }

    $parts = $line -split "[:$fullWidthColon]", 2
    if ($parts.Count -eq 2 -and -not [string]::IsNullOrWhiteSpace($parts[1])) {
      $username = $parts[1].Trim()
      break
    }
  }

  if ([string]::IsNullOrWhiteSpace($username)) {
    throw "Could not find a username in $Path."
  }

  [pscustomobject]@{
    Username = $username
    Token = $tokenMatch.Value.Trim()
  }
}

function New-GitAskPass {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Directory
  )

  New-Item -ItemType Directory -Force -Path $Directory | Out-Null

  $scriptPath = Join-Path $Directory "git-askpass.ps1"
  $commandPath = Join-Path $Directory "git-askpass.cmd"
  $scriptLines = @(
    'param(',
    '  [string] $Prompt',
    ')',
    '',
    'if ($Prompt -match "(?i)username") {',
    '  [Console]::Out.Write($env:GIT_PUSH_USERNAME)',
    '  exit 0',
    '}',
    '',
    'if ($Prompt -match "(?i)password|token") {',
    '  [Console]::Out.Write($env:GIT_PUSH_TOKEN)',
    '  exit 0',
    '}',
    '',
    '[Console]::Out.Write("")'
  )
  $commandLines = @(
    '@echo off',
    "powershell -NoProfile -ExecutionPolicy Bypass -File ""$scriptPath"" %*"
  )

  Set-Content -LiteralPath $scriptPath -Value $scriptLines -Encoding UTF8
  Set-Content -LiteralPath $commandPath -Value $commandLines -Encoding ASCII

  [pscustomobject]@{
    Script = $scriptPath
    Command = $commandPath
  }
}

function Test-RemoteAccess {
  param(
    [Parameter(Mandatory = $true)]
    [string] $RepositoryUrl,

    [Parameter(Mandatory = $true)]
    [string] $Branch
  )

  Write-Host "Checking GitHub access for $Branch..."
  $result = Invoke-GitChecked @("-c", "http.version=HTTP/1.1", "ls-remote", "--heads", $RepositoryUrl, $Branch) -Attempts $networkGitAttempts -NoThrow
  if ($result.ExitCode -ne 0) {
    $message = ($result.Output | Out-String).Trim()
    if ($message -match "Recv failure|Connection was reset|Connection reset|Could not resolve host|Failed to connect|Couldn't connect|timed out|Connection refused|curl 28|curl 35|curl 56") {
      throw "Cannot connect to GitHub. Check your network, proxy, VPN, or DNS, then try again.`n$message"
    }

    if ($message -match "Authentication failed|could not read Username|Repository not found|403|401") {
      throw "GitHub authentication failed, or the token cannot access this repository.`n$message"
    }

    throw "Could not access the remote repository.`n$message"
  }

  if (-not $result.Output) {
    throw "Remote branch not found: $Branch"
  }
}

try {
  $credentials = Get-PushCredentials -Path $credentialPath
  $env:GIT_PUSH_USERNAME = $credentials.Username
  $env:GIT_PUSH_TOKEN = $credentials.Token
  $env:GIT_TERMINAL_PROMPT = "0"

  if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = Read-Host "Commit message"
  }

  if ([string]::IsNullOrWhiteSpace($Message)) {
    throw "Commit message cannot be empty."
  }

  Set-Location -LiteralPath $projectRoot

  if (Test-Path -LiteralPath $tempRoot) {
    Write-Host "Removing old temporary checkout..."
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
  }

  New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
  $askPassRoot = Join-Path $env:ProgramData ("CodexGitAskPass\push-frontend-{0}" -f $PID)
  $askPass = New-GitAskPass -Directory $askPassRoot
  $askPassScript = $askPass.Script
  $askPassCommand = $askPass.Command
  $env:GIT_ASKPASS = $askPassCommand

  Test-RemoteAccess -RepositoryUrl $repoUrl -Branch $branchName

  Write-Host "Cloning repository branch $branchName..."
  Invoke-GitChecked @("-c", "http.version=HTTP/1.1", "clone", "--branch", $branchName, $repoUrl, $repoDir) -Attempts $networkGitAttempts

  Write-Host "Copying current pro project to frontend_dashboard..."
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
  robocopy $projectRoot $targetDir /MIR /XD node_modules dist .push-tmp SmartAgriBrain /XF $credentialFileName dev-server.log dev-server.err.log tsconfig.tsbuildinfo /NFL /NDL /NJH /NJS /NC /NS
  if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with exit code $LASTEXITCODE"
  }

  $copiedCredentialPath = Join-Path $targetDir (Join-Path "scripts\git" $credentialFileName)
  if (Test-Path -LiteralPath $copiedCredentialPath) {
    Remove-Item -LiteralPath $copiedCredentialPath -Force
  }

  Set-Location -LiteralPath $repoDir
  Invoke-GitChecked @("add", "frontend_dashboard")

  $changes = & git status --porcelain
  if (-not $changes) {
    Write-Host "No changes to commit."
  } else {
    Invoke-GitChecked @("commit", "-m", $Message.Trim())
    Invoke-GitChecked @("-c", "http.version=HTTP/1.1", "push", "origin", $branchName) -Attempts $networkGitAttempts
  }

  Write-Host "Done. Frontend dashboard has been pushed."
} finally {
  Remove-Item Env:\GIT_PUSH_USERNAME -ErrorAction SilentlyContinue
  Remove-Item Env:\GIT_PUSH_TOKEN -ErrorAction SilentlyContinue
  Remove-Item Env:\GIT_ASKPASS -ErrorAction SilentlyContinue
  Remove-Item Env:\GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue

  if ($askPassScript -and (Test-Path -LiteralPath $askPassScript)) {
    Remove-Item -LiteralPath $askPassScript -Force -ErrorAction SilentlyContinue
  }

  if ($askPassCommand -and (Test-Path -LiteralPath $askPassCommand)) {
    Remove-Item -LiteralPath $askPassCommand -Force -ErrorAction SilentlyContinue
  }

  if ($askPassRoot -and (Test-Path -LiteralPath $askPassRoot)) {
    Remove-Item -LiteralPath $askPassRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
