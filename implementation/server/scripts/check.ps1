# The one command every task runs before committing (PowerShell twin of check.sh).
# Build-out exception: clippy::todo is allowed until Task 21.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Run($cmd) { & $cmd[0] $cmd[1..($cmd.Length - 1)]; if ($LASTEXITCODE -ne 0) { throw "failed: $($cmd -join ' ')" } }
Run @('cargo', 'fmt', '--all', '--check')
Run @('cargo', 'clippy', '--workspace', '--all-targets', '--', '-D', 'warnings', '-A', 'clippy::todo')
Run @('cargo', 'test', '--workspace')
Run @('cargo', 'deny', 'check')
Write-Host 'CHECK OK'
