param(
  [string] $Message,
  [ValidateRange(1, 10)]
  [int] $MaxNetworkAttempts = 3,
  [switch] $DryRun,
  [switch] $ValidateOnly
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).ProviderPath
$repoUrl = "ssh://git@ssh.github.com:443/nagnud/SmartAgriBrain.git"
$branchName = "feature/frontend"
$cacheRoot = Join-Path $projectRoot ".push-cache"
$repoDir = Join-Path $cacheRoot "SmartAgriBrain"
$targetDir = Join-Path $repoDir "frontend_dashboard"
$legacyTempRoot = Join-Path $projectRoot ".push-tmp"
$sshDirectory = Join-Path $HOME ".ssh"
$sshKeyPath = Join-Path $sshDirectory "smartagribrain_ed25519"
$sshPublicKeyPath = "$sshKeyPath.pub"
$sshVerificationPath = "$sshKeyPath.verified"
$networkCommandTimeoutSeconds = 90
$networkLowSpeedTimeSeconds = 45
$mutex = $null
$mutexAcquired = $false

function Write-Step {
  param([string] $Text)
  Write-Host ""
  Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Success {
  param([string] $Text)
  Write-Host $Text -ForegroundColor Green
}

function Test-CommandAvailable {
  param([Parameter(Mandatory = $true)][string] $Name)
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-TransientNetworkError {
  param([string] $Text)
  return $Text -match "timed out|timeout|Operation too slow|Connection reset|Connection was reset|Connection closed|Connection refused|Failed to connect|Could not resolve|Could not resolve hostname|Temporary failure|Network is unreachable|No route to host|kex_exchange_identification|early EOF|remote end hung up|RPC failed|HTTP/2 stream|SSL_ERROR_SYSCALL|curl 28|curl 35|curl 56|408|429|5\d\d"
}

function Test-AuthenticationError {
  param([string] $Text)
  return $Text -match "Permission denied \(publickey\)|Authentication failed|Repository not found|Could not read from remote repository|access rights|ERROR: Permission|403|401"
}

function Test-NonFastForwardError {
  param([string] $Text)
  return $Text -match "non-fast-forward|fetch first|rejected.*(behind|non-fast-forward|fetch first)|Updates were rejected"
}

function Test-SecretScanningError {
  param([string] $Text)
  return $Text -match "secret scanning|push protection|GH013|repository rule violations|protected secret|blocked by push protection"
}

function Get-RetryDelaySeconds {
  param([int] $Attempt)
  return [int][Math]::Min(60, 5 * [Math]::Pow(2, [Math]::Max(0, $Attempt - 1)))
}

function ConvertTo-CommandLineArgument {
  param([Parameter(Mandatory = $true)][AllowEmptyString()][string] $Value)

  if ($Value.Length -eq 0) {
    return '""'
  }

  if ($Value -notmatch '[\s"]') {
    return $Value
  }

  $escaped = $Value -replace '\\(?=\\*")', '$0$0'
  $escaped = $escaped -replace '"', '\"'
  $escaped = $escaped -replace '(\\+)$', '$1$1'
  return '"' + $escaped + '"'
}

function Stop-ProcessTree {
  param([Parameter(Mandatory = $true)][int] $ProcessId)

  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
  foreach ($child in $children) {
    Stop-ProcessTree -ProcessId $child.ProcessId
  }
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Invoke-ProcessCaptured {
  param(
    [Parameter(Mandatory = $true)][string] $FileName,
    [Parameter(Mandatory = $true)][AllowEmptyString()][string[]] $Arguments,
    [string] $WorkingDirectory,
    [int] $TimeoutSeconds = 0
  )

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo.FileName = $FileName
  $process.StartInfo.Arguments = ($Arguments | ForEach-Object { ConvertTo-CommandLineArgument -Value $_ }) -join " "
  if ($WorkingDirectory) {
    $process.StartInfo.WorkingDirectory = $WorkingDirectory
  }
  $process.StartInfo.UseShellExecute = $false
  $process.StartInfo.RedirectStandardOutput = $true
  $process.StartInfo.RedirectStandardError = $true
  $process.StartInfo.CreateNoWindow = $true

  [void]$process.Start()
  $stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $stderrTask = $process.StandardError.ReadToEndAsync()
  $finished = $true
  if ($TimeoutSeconds -gt 0) {
    $finished = $process.WaitForExit($TimeoutSeconds * 1000)
  } else {
    $process.WaitForExit()
  }

  if (-not $finished) {
    Stop-ProcessTree -ProcessId $process.Id
    return [pscustomobject]@{
      ExitCode = 124
      Output = @("Command timed out after ${TimeoutSeconds}s: $FileName $($Arguments -join ' ')")
    }
  }

  $output = @()
  if ($stdoutTask.Result) {
    $output += ($stdoutTask.Result -split "`r?`n" | Where-Object { $_ -ne "" })
  }
  if ($stderrTask.Result) {
    $output += ($stderrTask.Result -split "`r?`n" | Where-Object { $_ -ne "" })
  }

  return [pscustomobject]@{
    ExitCode = $process.ExitCode
    Output = @($output)
  }
}

function Invoke-GitCaptured {
  param(
    [Parameter(Mandatory = $true)][string[]] $Arguments,
    [string] $WorkingDirectory,
    [int] $TimeoutSeconds = 0
  )

  return Invoke-ProcessCaptured -FileName "git" -Arguments $Arguments -WorkingDirectory $WorkingDirectory -TimeoutSeconds $TimeoutSeconds
}

function Invoke-GitChecked {
  param(
    [Parameter(Mandatory = $true)][string[]] $Arguments,
    [string] $WorkingDirectory,
    [int] $Attempts = 1,
    [switch] $Network,
    [switch] $NoThrow
  )

  $gitArguments = @()
  if ($Network) {
    $gitArguments += @(
      "-c", "http.lowSpeedLimit=1",
      "-c", "http.lowSpeedTime=$networkLowSpeedTimeSeconds",
      "-c", "core.longpaths=true"
    )
  }
  $gitArguments += $Arguments

  $lastResult = $null
  $safeAttempts = [Math]::Max(1, $Attempts)
  for ($attempt = 1; $attempt -le $safeAttempts; $attempt++) {
    $timeout = if ($Network) { $networkCommandTimeoutSeconds } else { 0 }
    $lastResult = Invoke-GitCaptured -Arguments $gitArguments -WorkingDirectory $WorkingDirectory -TimeoutSeconds $timeout
    $text = ($lastResult.Output | Out-String).Trim()

    if ($lastResult.ExitCode -eq 0) {
      if ($text -and -not $NoThrow) {
        Write-Host $text
      }
      return $lastResult
    }

    if ($attempt -lt $safeAttempts -and (Test-TransientNetworkError -Text $text)) {
      $delay = Get-RetryDelaySeconds -Attempt $attempt
      Write-Warning ("GitHub connection failed. Retrying in {0}s ({1}/{2})." -f $delay, $attempt, $safeAttempts)
      if ($text) { Write-Host $text }
      Start-Sleep -Seconds $delay
      continue
    }

    if ($NoThrow) {
      return $lastResult
    }

    throw "git $($gitArguments -join ' ') failed with exit code $($lastResult.ExitCode).`n$text"
  }
}

function Assert-Prerequisites {
  foreach ($command in @("git", "ssh", "ssh-keygen", "robocopy")) {
    if (-not (Test-CommandAvailable -Name $command)) {
      throw "Required command '$command' is not available. Install Git for Windows with OpenSSH support."
    }
  }

  $gitVersion = Invoke-GitCaptured -Arguments @("--version")
  if ($gitVersion.ExitCode -ne 0) {
    throw "Git is installed but cannot be executed."
  }
  Write-Host (($gitVersion.Output | Out-String).Trim())
}

function Enter-SingleInstance {
  $script:mutex = New-Object System.Threading.Mutex($false, "Local\SmartAgriBrainPushFrontend")
  try {
    $script:mutexAcquired = $script:mutex.WaitOne(0)
  } catch [System.Threading.AbandonedMutexException] {
    $script:mutexAcquired = $true
  }

  if (-not $script:mutexAcquired) {
    throw "Another push-frontend window is already running. Close it or wait for it to finish."
  }
}

function Set-SshEnvironment {
  $escapedKeyPath = $sshKeyPath.Replace('"', '\"')
  $env:GIT_SSH_COMMAND = "ssh -i `"$escapedKeyPath`" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
  $env:GIT_SSH_VARIANT = "ssh"
  $env:GIT_TERMINAL_PROMPT = "0"
}

function Invoke-SshAuthenticationTest {
  $arguments = @(
    "-T", "-p", "443",
    "-i", $sshKeyPath,
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "git@ssh.github.com"
  )
  $result = Invoke-ProcessCaptured -FileName "ssh" -Arguments $arguments -TimeoutSeconds 30
  $text = ($result.Output | Out-String).Trim()

  if ($text -match "successfully authenticated") {
    Write-Success $text
    return $true
  }

  if ($text) { Write-Host $text }
  return $false
}

function Show-PublicKeySetup {
  $publicKey = (Get-Content -LiteralPath $sshPublicKeyPath -Raw).Trim()
  try {
    if (Test-CommandAvailable -Name "Set-Clipboard") {
      Set-Clipboard -Value $publicKey
    } else {
      $publicKey | clip.exe
    }
    Write-Host "The public key has been copied to the clipboard."
  } catch {
    Write-Warning "Could not copy the public key automatically. Copy it from: $sshPublicKeyPath"
  }

  Write-Host ""
  Write-Host "One-time GitHub setup:" -ForegroundColor Yellow
  Write-Host "1. On the GitHub page that opens, set a title such as SmartAgriBrain-PC."
  Write-Host "2. Paste the copied public key into the Key box and click Add SSH key."
  Write-Host "3. Return to this window and press Enter."
  try {
    Start-Process "https://github.com/settings/ssh/new"
  } catch {
    Write-Host "Open this page manually: https://github.com/settings/ssh/new"
  }
}

function Ensure-SshIdentity {
  if ((Test-Path -LiteralPath $sshKeyPath) -xor (Test-Path -LiteralPath $sshPublicKeyPath)) {
    throw "The dedicated SSH key pair is incomplete. Preserve any existing file, then repair these paths: $sshKeyPath and $sshPublicKeyPath"
  }

  $createdNow = $false
  if (-not (Test-Path -LiteralPath $sshKeyPath)) {
    Write-Step "Creating a dedicated GitHub SSH key (one-time setup)"
    New-Item -ItemType Directory -Force -Path $sshDirectory | Out-Null
    $keyResult = Invoke-ProcessCaptured -FileName "ssh-keygen" -Arguments @(
      "-t", "ed25519",
      "-C", "SmartAgriBrain push key",
      "-f", $sshKeyPath,
      "-N", ""
    ) -TimeoutSeconds 30
    if ($keyResult.ExitCode -ne 0) {
      throw "Could not create the SSH key.`n$(($keyResult.Output | Out-String).Trim())"
    }
    $createdNow = $true
  }

  if ($createdNow -or -not (Test-Path -LiteralPath $sshVerificationPath)) {
    Show-PublicKeySetup
    [void](Read-Host "Press Enter after adding the SSH key to your GitHub account")
    if (-not (Invoke-SshAuthenticationTest)) {
      throw "GitHub did not accept the new SSH key yet. Confirm that the key was added to the invited GitHub account, then run this same script again."
    }
    [System.IO.File]::WriteAllText($sshVerificationPath, "Verified by push-frontend.ps1 on $([DateTime]::Now.ToString('s'))")
    return
  }

  Set-SshEnvironment
}

function Get-GitDivergence {
  $result = Invoke-GitCaptured -Arguments @("rev-list", "--left-right", "--count", "origin/$branchName...$branchName") -WorkingDirectory $repoDir
  if ($result.ExitCode -ne 0) {
    return [pscustomobject]@{ Behind = 0; Ahead = 0 }
  }

  $parts = ((($result.Output | Select-Object -First 1) -as [string]).Trim()) -split "\s+"
  $behind = 0
  $ahead = 0
  if ($parts.Count -ge 1) { [void][int]::TryParse($parts[0], [ref]$behind) }
  if ($parts.Count -ge 2) { [void][int]::TryParse($parts[1], [ref]$ahead) }
  return [pscustomobject]@{ Behind = $behind; Ahead = $ahead }
}

function Get-LocalAheadCount {
  if (-not (Test-Path -LiteralPath (Join-Path $repoDir ".git"))) { return 0 }
  $result = Invoke-GitCaptured -Arguments @("rev-list", "--count", "origin/$branchName..$branchName") -WorkingDirectory $repoDir
  $count = 0
  if ($result.ExitCode -eq 0 -and [int]::TryParse(($result.Output | Select-Object -First 1), [ref]$count)) {
    return $count
  }
  return 0
}

function Reset-GeneratedCacheWorktree {
  $status = Invoke-GitCaptured -Arguments @("status", "--porcelain") -WorkingDirectory $repoDir
  if (($status.Output | Out-String).Trim()) {
    Write-Warning "Cleaning unfinished generated files left in .push-cache from a previous run."
    Invoke-GitChecked -Arguments @("reset", "--hard", "HEAD") -WorkingDirectory $repoDir | Out-Null
    Invoke-GitChecked -Arguments @("clean", "-fd", "--", "frontend_dashboard") -WorkingDirectory $repoDir | Out-Null
  }
}

function Backup-QueuedBranch {
  param([string] $Prefix)
  $backupBranch = "$Prefix/$((Get-Date).ToString('yyyyMMdd-HHmmss'))-$PID"
  Invoke-GitChecked -Arguments @("branch", $backupBranch, "HEAD") -WorkingDirectory $repoDir | Out-Null
  Write-Warning "Queued commits were preserved on local backup branch: $backupBranch"
  return $backupBranch
}

function Reconcile-WithRemote {
  $divergence = Get-GitDivergence
  if ($divergence.Ahead -gt 0 -and $divergence.Behind -gt 0) {
    Write-Warning "Remote has $($divergence.Behind) new commit(s); rebasing $($divergence.Ahead) queued local commit(s)."
    $rebase = Invoke-GitChecked -Arguments @("rebase", "origin/$branchName") -WorkingDirectory $repoDir -NoThrow
    if ($rebase.ExitCode -eq 0) { return }

    $rebaseText = ($rebase.Output | Out-String).Trim()
    Invoke-GitChecked -Arguments @("rebase", "--abort") -WorkingDirectory $repoDir -NoThrow | Out-Null
    [void](Backup-QueuedBranch -Prefix "push-cache-conflict")
    Write-Warning "Queued commits conflicted with the remote. The backup is preserved; rebuilding a clean snapshot from the current pro project."
    if ($rebaseText) { Write-Host $rebaseText }
    Invoke-GitChecked -Arguments @("reset", "--hard", "origin/$branchName") -WorkingDirectory $repoDir | Out-Null
    Invoke-GitChecked -Arguments @("clean", "-fd", "--", "frontend_dashboard") -WorkingDirectory $repoDir | Out-Null
    return
  }

  if ($divergence.Behind -gt 0) {
    Invoke-GitChecked -Arguments @("reset", "--hard", "origin/$branchName") -WorkingDirectory $repoDir | Out-Null
    Invoke-GitChecked -Arguments @("clean", "-fd", "--", "frontend_dashboard") -WorkingDirectory $repoDir | Out-Null
  } elseif ($divergence.Ahead -gt 0) {
    Write-Warning "$($divergence.Ahead) local commit(s) are queued and will be pushed in this run."
  }
}

function Ensure-RepoCache {
  $gitDir = Join-Path $repoDir ".git"
  New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null

  if (Test-Path -LiteralPath $gitDir) {
    Write-Step "Preparing the persistent push queue"
    Invoke-GitChecked -Arguments @("remote", "set-url", "origin", $repoUrl) -WorkingDirectory $repoDir | Out-Null
    Invoke-GitChecked -Arguments @("checkout", $branchName) -WorkingDirectory $repoDir | Out-Null
    Reset-GeneratedCacheWorktree

    $refspec = "+refs/heads/${branchName}:refs/remotes/origin/${branchName}"
    $fetch = Invoke-GitChecked -Arguments @("fetch", "--prune", "origin", $refspec) -WorkingDirectory $repoDir -Network -Attempts $MaxNetworkAttempts -NoThrow
    if ($fetch.ExitCode -ne 0) {
      $fetchText = ($fetch.Output | Out-String).Trim()
      if (Test-TransientNetworkError -Text $fetchText) {
        Write-Warning "GitHub is unreachable. Continuing with the existing queue; any new commit will remain local."
        if ($fetchText) { Write-Host $fetchText }
        return "offline"
      }
      if (Test-AuthenticationError -Text $fetchText) {
        throw "SSH authentication succeeded locally, but GitHub denied repository access. Confirm that this GitHub account accepted the invitation and has Write permission.`n$fetchText"
      }
      throw "Could not update the cached repository.`n$fetchText"
    }

    Reconcile-WithRemote
    return "online"
  }

  if (Test-Path -LiteralPath $repoDir) {
    throw "The push-cache folder exists but is not a Git repository: $repoDir. Preserve it and ask an agent to inspect it; it will not be deleted automatically."
  }

  Write-Step "Creating the persistent push queue"
  $clone = Invoke-GitChecked -Arguments @("clone", "--single-branch", "--branch", $branchName, $repoUrl, $repoDir) -Network -Attempts $MaxNetworkAttempts -NoThrow
  if ($clone.ExitCode -ne 0) {
    $cloneText = ($clone.Output | Out-String).Trim()
    if (Test-TransientNetworkError -Text $cloneText) {
      throw "The first cache checkout requires a working network connection. No project files were deleted; run this script again when GitHub is reachable.`n$cloneText"
    }
    throw "Could not clone the repository. Confirm SSH key access and repository permission.`n$cloneText"
  }
  return "online"
}

function Set-LocalGitIdentity {
  $name = (Invoke-GitCaptured -Arguments @("config", "user.name") -WorkingDirectory $repoDir).Output | Select-Object -First 1
  $email = (Invoke-GitCaptured -Arguments @("config", "user.email") -WorkingDirectory $repoDir).Output | Select-Object -First 1
  if ([string]::IsNullOrWhiteSpace($name)) {
    $name = if ($env:USERNAME) { $env:USERNAME } else { "SmartAgriBrain Contributor" }
    Invoke-GitChecked -Arguments @("config", "user.name", $name) -WorkingDirectory $repoDir | Out-Null
  }
  if ([string]::IsNullOrWhiteSpace($email)) {
    Invoke-GitChecked -Arguments @("config", "user.email", "$name@users.noreply.github.com") -WorkingDirectory $repoDir | Out-Null
  }
  Invoke-GitChecked -Arguments @("config", "core.autocrlf", "false") -WorkingDirectory $repoDir | Out-Null
  Invoke-GitChecked -Arguments @("config", "core.safecrlf", "false") -WorkingDirectory $repoDir | Out-Null
}

function Get-ForwardingPushScriptContent {
@'
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
'@
}

function Install-ForwardingPushScriptsInCheckout {
  $gitScriptDir = Join-Path $targetDir "scripts\git"
  New-Item -ItemType Directory -Force -Path $gitScriptDir | Out-Null
  Set-Content -LiteralPath (Join-Path $gitScriptDir "push-frontend.ps1") -Value (Get-ForwardingPushScriptContent) -Encoding ASCII
  Set-Content -LiteralPath (Join-Path $gitScriptDir "push-frontend.bat") -Value @(
    "@echo off",
    "chcp 65001 >nul",
    "powershell -NoProfile -ExecutionPolicy Bypass -File ""%~dp0push-frontend.ps1"" %*",
    "pause"
  ) -Encoding ASCII
}

function Copy-ProjectToCheckout {
  Write-Step "Mirroring the current pro project to frontend_dashboard"
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

  & robocopy $projectRoot $targetDir /MIR `
    /XD node_modules dist .push-cache .push-tmp .git SmartAgriBrain .venv venv __pycache__ .pytest_cache .mypy_cache .ssh `
    /XF .env push*.md *.pem *.key id_rsa* id_ed25519* *.log *.err.log *.codex.log *.codex.err.log *.db *.sqlite *.sqlite3 tsconfig.tsbuildinfo `
    /NFL /NDL /NJH /NJS /NC /NS

  if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with exit code $LASTEXITCODE"
  }

  Install-ForwardingPushScriptsInCheckout
}

function Commit-ProjectSnapshot {
  Invoke-GitChecked -Arguments @("add", "-A", "frontend_dashboard") -WorkingDirectory $repoDir | Out-Null
  $status = Invoke-GitCaptured -Arguments @("status", "--porcelain", "--", "frontend_dashboard") -WorkingDirectory $repoDir
  if (-not (($status.Output | Out-String).Trim())) {
    Write-Host "No new project changes to commit."
    return $false
  }

  $commitMessage = $Message
  if ([string]::IsNullOrWhiteSpace($commitMessage)) {
    $commitMessage = Read-Host "Commit message"
  }
  if ([string]::IsNullOrWhiteSpace($commitMessage)) {
    throw "Commit message cannot be empty."
  }

  Invoke-GitChecked -Arguments @("commit", "-m", $commitMessage.Trim()) -WorkingDirectory $repoDir | Out-Null
  Write-Success "Project snapshot committed to the persistent queue."
  return $true
}

function Push-QueuedCommits {
  if ((Get-LocalAheadCount) -eq 0) {
    return "nothing"
  }

  if ($DryRun) {
    Write-Warning "DryRun is enabled. Commits remain queued locally and were not pushed."
    Invoke-GitChecked -Arguments @("log", "-3", "--oneline") -WorkingDirectory $repoDir | Out-Null
    return "queued"
  }

  Write-Step "Pushing queued commits to GitHub through SSH port 443"
  $push = Invoke-GitChecked -Arguments @("push", "origin", $branchName) -WorkingDirectory $repoDir -Network -Attempts $MaxNetworkAttempts -NoThrow
  $text = ($push.Output | Out-String).Trim()
  if ($push.ExitCode -eq 0) {
    if ($text) { Write-Host $text }
    return "pushed"
  }

  if (Test-TransientNetworkError -Text $text) {
    Write-Warning "GitHub is unreachable. Your commits are saved locally in .push-cache and have NOT been uploaded."
    if ($text) { Write-Host $text }
    return "queued"
  }
  if (Test-NonFastForwardError -Text $text) {
    Write-Warning "The remote branch changed during this run. The script will synchronize and retry without force-pushing."
    if ($text) { Write-Host $text }
    return "resync"
  }
  if (Test-SecretScanningError -Text $text) {
    throw "GitHub blocked the push because a secret or API key was detected. The commit remains local; remove the secret instead of bypassing protection.`n$text"
  }
  if (Test-AuthenticationError -Text $text) {
    throw "GitHub denied authentication or repository write access. Confirm that this SSH key belongs to the invited account and that the account has Write permission.`n$text"
  }
  if ($text -match "protected branch|protected branch hook declined|rule violations|required status check") {
    throw "GitHub branch protection or a repository rule blocked the push. The commit remains queued locally.`n$text"
  }
  throw "Push failed for a non-network reason. The commit remains queued locally.`n$text"
}

function Resync-AfterRejectedPush {
  $refspec = "+refs/heads/${branchName}:refs/remotes/origin/${branchName}"
  $fetch = Invoke-GitChecked -Arguments @("fetch", "--prune", "origin", $refspec) -WorkingDirectory $repoDir -Network -Attempts $MaxNetworkAttempts -NoThrow
  if ($fetch.ExitCode -ne 0) {
    $text = ($fetch.Output | Out-String).Trim()
    if (Test-TransientNetworkError -Text $text) { return $false }
    throw "Could not resynchronize after a rejected push.`n$text"
  }
  Reconcile-WithRemote
  return $true
}

function Invoke-Validation {
  Assert-Prerequisites
  Write-Step "Validating reusable push configuration"
  Write-Host "Project source: $projectRoot"
  Write-Host "Remote: $repoUrl"
  Write-Host "Branch: $branchName"
  Write-Host "Persistent queue: $repoDir"
  if (Test-Path -LiteralPath $sshKeyPath) {
    Write-Host "Dedicated SSH private key: present"
    if (Test-Path -LiteralPath $sshVerificationPath) {
      Write-Host "GitHub SSH binding: previously verified"
    } else {
      Write-Warning "GitHub SSH binding has not been verified. The next normal run will open the SSH key page."
    }
  } else {
    Write-Warning "Dedicated SSH key has not been created yet. The first normal run will create it and open GitHub's SSH key page."
  }
  if (Test-Path -LiteralPath (Join-Path $repoDir ".git")) {
    Write-Host "Queued local commits: $(Get-LocalAheadCount)"
  } else {
    Write-Host "Persistent queue: not created yet"
  }
  if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "push$([char]0x8F93)$([char]0x5165).md")) {
    throw "A plaintext credential file still exists beside the script. Remove it and revoke its token before using this workflow."
  }
  Write-Success "Validation completed. No remote repository changes were made."
}

try {
  Enter-SingleInstance

  if ($ValidateOnly) {
    Invoke-Validation
    exit 0
  }

  Assert-Prerequisites
  Ensure-SshIdentity
  Set-SshEnvironment

  if (Test-Path -LiteralPath $legacyTempRoot) {
    Write-Warning "The legacy .push-tmp directory is no longer used and was left untouched."
  }

  $queueState = Ensure-RepoCache
  Set-LocalGitIdentity
  Copy-ProjectToCheckout
  [void](Commit-ProjectSnapshot)

  $finalState = "queued"
  for ($cycle = 1; $cycle -le 3; $cycle++) {
    $pushState = Push-QueuedCommits
    if ($pushState -eq "pushed" -or $pushState -eq "nothing") {
      $finalState = "synchronized"
      break
    }
    if ($pushState -eq "queued") {
      $finalState = "queued"
      break
    }
    if ($pushState -eq "resync") {
      if (-not (Resync-AfterRejectedPush)) {
        $finalState = "queued"
        break
      }
      Copy-ProjectToCheckout
      [void](Commit-ProjectSnapshot)
    }
  }

  Write-Step "Final status"
  if ($finalState -eq "synchronized" -and (Get-LocalAheadCount) -eq 0) {
    Write-Success "SUCCESS: frontend_dashboard is synchronized with GitHub."
  } else {
    Write-Warning "NOT UPLOADED YET: commits are safely queued in .push-cache."
    Write-Host "When the network is available, run this same push-frontend.bat again. No script rewrite is needed."
    exit 2
  }
} catch {
  Write-Host ""
  Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
} finally {
  Remove-Item Env:\GIT_SSH_COMMAND -ErrorAction SilentlyContinue
  Remove-Item Env:\GIT_SSH_VARIANT -ErrorAction SilentlyContinue
  Remove-Item Env:\GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
  if ($mutexAcquired -and $mutex) {
    try { $mutex.ReleaseMutex() } catch { }
  }
  if ($mutex) { $mutex.Dispose() }
}
