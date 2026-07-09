param(
  [string] $Message,
  [int] $MaxNetworkAttempts = 8,
  [switch] $DryRun,
  [switch] $ValidateOnly
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
$repoUrl = "https://github.com/nagnud/SmartAgriBrain.git"
$branchName = "feature/frontend"
$cacheRoot = Join-Path $projectRoot ".push-cache"
$repoDir = Join-Path $cacheRoot "SmartAgriBrain"
$targetDir = Join-Path $repoDir "frontend_dashboard"
$legacyTempRoot = Join-Path $projectRoot ".push-tmp"
$credentialFileName = "push$([char]0x8F93)$([char]0x5165).md"
$credentialPath = Join-Path $PSScriptRoot $credentialFileName
$askPassRoot = $null
$askPassScript = $null
$askPassCommand = $null

function Write-Step {
  param([string] $Text)
  Write-Host ""
  Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Info {
  param([string] $Text)
  Write-Host $Text
}

function Test-TransientGitNetworkError {
  param([string] $Message)

  return $Message -match "Recv failure|Connection was reset|Connection reset|Failed to connect|Couldn't connect|timed out|Could not resolve host|curl 28|curl 35|curl 56|HTTP/2 stream|SSL_read|SSL_ERROR_SYSCALL|schannel|RPC failed|early EOF|remote end hung up|Operation timed out|The requested URL returned error: 408|The requested URL returned error: 429|The requested URL returned error: 5\d\d"
}

function Test-NonFastForwardError {
  param([string] $Message)

  return $Message -match "non-fast-forward|fetch first|rejected.*behind|failed to push some refs"
}

function Get-RetryDelaySeconds {
  param([int] $Attempt)

  $delay = [Math]::Min(60, 5 * [Math]::Pow(2, [Math]::Max(0, $Attempt - 1)))
  return [int]$delay
}

function Invoke-GitCaptured {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Arguments,

    [string] $WorkingDirectory
  )

  $previousLocation = Get-Location
  $previousErrorActionPreference = $ErrorActionPreference
  try {
    if ($WorkingDirectory) {
      Set-Location -LiteralPath $WorkingDirectory
    }
    $ErrorActionPreference = "Continue"
    $output = & git @Arguments 2>&1 | ForEach-Object { $_.ToString() }
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
    Set-Location -LiteralPath $previousLocation
  }

  [pscustomobject]@{
    ExitCode = $exitCode
    Output = @($output)
  }
}

function Invoke-GitChecked {
  param(
    [Parameter(Mandatory = $true)]
    [string[]] $Arguments,

    [string] $WorkingDirectory,

    [int] $Attempts = 1,

    [switch] $Network,

    [switch] $NoThrow
  )

  $gitArguments = @()
  if ($Network) {
    $gitArguments += @(
      "-c", "http.version=HTTP/1.1",
      "-c", "http.lowSpeedLimit=1",
      "-c", "http.lowSpeedTime=15",
      "-c", "http.postBuffer=524288000",
      "-c", "credential.helper=",
      "-c", "core.longpaths=true"
    )
  }
  $gitArguments += $Arguments

  $lastResult = $null
  $safeAttempts = [Math]::Max(1, $Attempts)
  for ($attempt = 1; $attempt -le $safeAttempts; $attempt++) {
    $lastResult = Invoke-GitCaptured -Arguments $gitArguments -WorkingDirectory $WorkingDirectory
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

    if ($attempt -lt $safeAttempts -and (Test-TransientGitNetworkError -Message $message)) {
      $delay = Get-RetryDelaySeconds -Attempt $attempt
      Write-Warning ("GitHub network error. Retry in {0}s ({1}/{2})." -f $delay, $attempt, $safeAttempts)
      if ($message) {
        Write-Host $message
      }
      Start-Sleep -Seconds $delay
      continue
    }

    if ($NoThrow) {
      return $lastResult
    }

    if ($message) {
      throw "git $($gitArguments -join ' ') failed with exit code $($lastResult.ExitCode).`n$message"
    }
    throw "git $($gitArguments -join ' ') failed with exit code $($lastResult.ExitCode)."
  }
}

function Get-CredentialPath {
  if (Test-Path -LiteralPath $credentialPath) {
    return $credentialPath
  }

  $candidate = Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter "push*.md" |
    Where-Object {
      $text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($_.FullName))
      $text -match "(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)"
    } |
    Select-Object -First 1

  if ($candidate) {
    return $candidate.FullName
  }

  throw "Credential file not found under $PSScriptRoot. Expected push input markdown with username and token."
}

function Get-PushCredentials {
  param([Parameter(Mandatory = $true)][string] $Path)

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

function Get-AskPassRoot {
  $roots = @()
  if ($env:ProgramData) {
    $roots += (Join-Path $env:ProgramData "CodexGitAskPass")
  }
  if ($env:SystemRoot) {
    $roots += (Join-Path $env:SystemRoot "Temp\CodexGitAskPass")
  }
  if ($env:SystemDrive) {
    $roots += (Join-Path $env:SystemDrive "CodexGitAskPass")
  }

  foreach ($root in $roots) {
    if ($root -match "[^\x00-\x7F]") {
      continue
    }

    try {
      New-Item -ItemType Directory -Force -Path $root | Out-Null
      $probe = Join-Path $root ("write-test-{0}.tmp" -f $PID)
      Set-Content -LiteralPath $probe -Value "ok" -Encoding ASCII
      Remove-Item -LiteralPath $probe -Force
      return (Join-Path $root ("push-frontend-{0}" -f $PID))
    } catch {
      continue
    }
  }

  throw "Cannot create an ASCII-only askpass directory. Tried ProgramData, Windows Temp, and SystemDrive."
}

function New-GitAskPass {
  param([Parameter(Mandatory = $true)][string] $Directory)

  New-Item -ItemType Directory -Force -Path $Directory | Out-Null

  $commandPath = Join-Path $Directory "git-askpass.cmd"
  $commandLines = @(
    '@echo off',
    'echo %* | findstr /I "username" >nul',
    'if not errorlevel 1 (',
    '  <nul set /p=%GIT_PUSH_USERNAME%',
    '  exit /b 0',
    ')',
    '<nul set /p=%GIT_PUSH_TOKEN%',
    'exit /b 0'
  )

  Set-Content -LiteralPath $commandPath -Value $commandLines -Encoding ASCII

  [pscustomobject]@{
    Script = $null
    Command = $commandPath
  }
}

function Test-GitAskPass {
  param([Parameter(Mandatory = $true)][string] $Command)

  $username = & $Command "Username for 'https://github.com':"
  if ($LASTEXITCODE -ne 0 -or $username -ne $env:GIT_PUSH_USERNAME) {
    throw "Git askpass username test failed. Command path: $Command"
  }

  $token = & $Command "Password for 'https://github.com':"
  if ($LASTEXITCODE -ne 0 -or $token -ne $env:GIT_PUSH_TOKEN) {
    throw "Git askpass token test failed. Command path: $Command"
  }
}

function Assert-GitAvailable {
  $result = Invoke-GitChecked @("--version") -NoThrow
  if ($result.ExitCode -ne 0) {
    throw "Git is not available in PATH. Install Git for Windows or add git.exe to PATH."
  }
  Write-Info (($result.Output | Out-String).Trim())
}

function Ensure-RepoCache {
  $gitDir = Join-Path $repoDir ".git"
  New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null

  if (Test-Path -LiteralPath $gitDir) {
    Write-Step "Updating cached repository"
    Invoke-GitChecked @("remote", "set-url", "origin", $repoUrl) -WorkingDirectory $repoDir
    Invoke-GitChecked @("checkout", $branchName) -WorkingDirectory $repoDir

    $fetchResult = Invoke-GitChecked @("fetch", "--prune", "origin", $branchName) -WorkingDirectory $repoDir -Network -Attempts $MaxNetworkAttempts -NoThrow
    $fetchMessage = ($fetchResult.Output | Out-String).Trim()
    if ($fetchResult.ExitCode -ne 0) {
      if (Test-TransientGitNetworkError -Message $fetchMessage) {
        Write-Warning "GitHub is unreachable right now. Continuing with cached checkout; this run will be queued locally if push also fails."
        if ($fetchMessage) {
          Write-Host $fetchMessage
        }
        return "stale-cache"
      }
      throw "Could not update cached repository.`n$fetchMessage"
    }

    $ahead = Get-LocalAheadCount
    if ($ahead -gt 0) {
      Write-Warning "There are $ahead local commit(s) waiting to be pushed. Keeping them and adding this run on top."
      return "updated-with-pending"
    }

    Invoke-GitChecked @("checkout", "-B", $branchName, "origin/$branchName") -WorkingDirectory $repoDir
    Invoke-GitChecked @("reset", "--hard", "origin/$branchName") -WorkingDirectory $repoDir
    Invoke-GitChecked @("clean", "-fd", "--", "frontend_dashboard") -WorkingDirectory $repoDir
    return "updated"
  }

  if (Test-Path -LiteralPath $repoDir) {
    Write-Warning "Cached repository folder exists but is not a valid git checkout. Recreating cache."
    Remove-Item -LiteralPath $repoDir -Recurse -Force
  }

  Write-Step "Cloning repository branch $branchName"
  Invoke-GitChecked @("clone", "--single-branch", "--branch", $branchName, $repoUrl, $repoDir) -Network -Attempts $MaxNetworkAttempts
  return "cloned"
}

function Get-LocalAheadCount {
  $result = Invoke-GitCaptured -Arguments @("rev-list", "--count", "origin/$branchName..$branchName") -WorkingDirectory $repoDir
  if ($result.ExitCode -ne 0) {
    return 0
  }

  $text = ($result.Output | Select-Object -First 1)
  $count = 0
  if ([int]::TryParse($text, [ref]$count)) {
    return $count
  }
  return 0
}

function Set-LocalGitIdentity {
  Invoke-GitChecked @("config", "user.name", $env:GIT_PUSH_USERNAME) -WorkingDirectory $repoDir
  Invoke-GitChecked @("config", "user.email", "$($env:GIT_PUSH_USERNAME)@users.noreply.github.com") -WorkingDirectory $repoDir
  Invoke-GitChecked @("config", "core.autocrlf", "false") -WorkingDirectory $repoDir
  Invoke-GitChecked @("config", "core.safecrlf", "false") -WorkingDirectory $repoDir
}

function Copy-ProjectToCheckout {
  Write-Step "Copying current pro project to frontend_dashboard"
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

  robocopy $projectRoot $targetDir /MIR `
    /XD node_modules dist .push-cache .push-tmp .git SmartAgriBrain `
    /XF $credentialFileName dev-server.log dev-server.err.log dev-server.codex.log dev-server.codex.err.log tsconfig.tsbuildinfo `
    /NFL /NDL /NJH /NJS /NC /NS

  if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with exit code $LASTEXITCODE"
  }

  $copiedCredential = Get-ChildItem -LiteralPath (Join-Path $targetDir "scripts\git") -File -Filter "push*.md" -ErrorAction SilentlyContinue |
    Where-Object {
      $content = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($_.FullName))
      $content -match "(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)"
    }
  foreach ($file in $copiedCredential) {
    Remove-Item -LiteralPath $file.FullName -Force
  }
}

function Commit-FrontendChanges {
  Invoke-GitChecked @("add", "-A", "frontend_dashboard") -WorkingDirectory $repoDir

  $status = Invoke-GitCaptured -Arguments @("status", "--porcelain", "--", "frontend_dashboard") -WorkingDirectory $repoDir
  if (-not (($status.Output | Out-String).Trim())) {
    Write-Host "No changes to commit."
    return $false
  }

  Invoke-GitChecked @("commit", "-m", $Message.Trim()) -WorkingDirectory $repoDir
  return $true
}

function Push-FrontendCommit {
  if ($DryRun) {
    Write-Host "Dry run enabled. Commit was created in cache but push was skipped."
    Invoke-GitChecked @("log", "-1", "--oneline") -WorkingDirectory $repoDir
    return $true
  }

  Write-Step "Pushing to GitHub"
  $result = Invoke-GitChecked @("push", "origin", $branchName) -WorkingDirectory $repoDir -Network -Attempts $MaxNetworkAttempts -NoThrow
  if ($result.ExitCode -eq 0) {
    $message = ($result.Output | Out-String).Trim()
    if ($message) {
      Write-Host $message
    }
    return $true
  }

  $message = ($result.Output | Out-String).Trim()
  if (Test-NonFastForwardError -Message $message) {
    Write-Warning "Remote branch changed during this run. The script will resync once and recommit."
    return $false
  }

  if ($message -match "Authentication failed|could not read Username|Repository not found|403|401") {
    throw "GitHub authentication failed, or the token cannot access this repository.`n$message"
  }

  if (Test-TransientGitNetworkError -Message $message) {
    Write-Warning "GitHub network is still unstable after $MaxNetworkAttempts attempts."
    Write-Warning "Your commit is saved locally in .push-cache and will be pushed automatically next time the network works."
    if ($message) {
      Write-Host $message
    }
    return "queued"
  }

  throw "Push failed.`n$message"
}

try {
  Assert-GitAvailable

  $actualCredentialPath = Get-CredentialPath
  $credentials = Get-PushCredentials -Path $actualCredentialPath
  $env:GIT_PUSH_USERNAME = $credentials.Username
  $env:GIT_PUSH_TOKEN = $credentials.Token
  $env:GIT_TERMINAL_PROMPT = "0"

  $askPassRoot = Get-AskPassRoot
  $askPass = New-GitAskPass -Directory $askPassRoot
  $askPassScript = $askPass.Script
  $askPassCommand = $askPass.Command
  $env:GIT_ASKPASS = $askPassCommand
  Test-GitAskPass -Command $askPassCommand

  if ($ValidateOnly) {
    Write-Host "Validation OK. Credential file, username, token format, git executable, and askpass authentication helper are available."
    exit 0
  }

  if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = Read-Host "Commit message"
  }
  if ([string]::IsNullOrWhiteSpace($Message)) {
    throw "Commit message cannot be empty."
  }

  if (Test-Path -LiteralPath $legacyTempRoot) {
    Write-Step "Removing old legacy temporary checkout"
    Remove-Item -LiteralPath $legacyTempRoot -Recurse -Force
  }

  $completed = $false
  $queued = $false
  for ($cycle = 1; $cycle -le 2 -and -not $completed -and -not $queued; $cycle++) {
    $cacheState = Ensure-RepoCache
    Set-LocalGitIdentity
    Copy-ProjectToCheckout
    $hasCommit = Commit-FrontendChanges
    if (-not $hasCommit) {
      if ((Get-LocalAheadCount) -gt 0) {
        $pushState = Push-FrontendCommit
        if ($pushState -eq "queued") {
          $queued = $true
        } elseif ($pushState -eq $true) {
          $completed = $true
        }
      } else {
        $completed = $true
      }
      break
    }
    $pushState = Push-FrontendCommit
    if ($pushState -eq "queued") {
      $queued = $true
    } elseif ($pushState -eq $true) {
      $completed = $true
    }
  }

  if (-not $completed -and -not $queued) {
    throw "Push could not be completed after resyncing the remote branch."
  }

  Write-Step "Done"
  if ($queued) {
    Write-Host "Saved locally. GitHub is unreachable, so the commit is queued in .push-cache."
    Write-Host "Run this script again when the network is stable; it will push the queued commit automatically."
  } else {
    Write-Host "Frontend dashboard is synchronized with GitHub."
  }
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
