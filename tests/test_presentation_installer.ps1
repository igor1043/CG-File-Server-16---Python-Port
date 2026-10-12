# Isolated copies only. Does not install into any FIFA directory or load a DLL.
$ErrorActionPreference = 'Stop'
$taskRepo = Split-Path $PSScriptRoot -Parent
$taskPackage = Join-Path $taskRepo 'dist\MatchPresentation'
$taskFixture = Join-Path $taskRepo ('build\presentation-install-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskFixture | Out-Null
Copy-Item -LiteralPath (Join-Path $taskRepo 'native_mods\README.md') -Destination (Join-Path $taskFixture 'fifa16.exe')
foreach ($taskRelative in @('ModCarrerMode\mods\mascot_single\mascot_goal_line_v26.dll','ModCarrerMode\mods\stadium_pyrotechnics\stadium_pyrotechnics.dll')) {
    $taskTarget = Join-Path $taskFixture $taskRelative
    New-Item -ItemType Directory -Path (Split-Path $taskTarget -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $taskPackage $taskRelative) -Destination $taskTarget
}
# Only this test process replaces process detection; the target is the unique
# fixture above, and no generated executable is ever run.
function Get-Process { param([string]$Name,[string]$ErrorAction) return $null }
& (Join-Path $taskPackage 'Install-MatchPresentation.ps1') -GameRoot $taskFixture
$taskChanged = Join-Path $taskFixture 'ModCarrerMode\mods\stadium_pyrotechnics\stadium_pyrotechnics.dll'
Copy-Item -LiteralPath (Join-Path $taskRepo 'native_mods\README.md') -Destination $taskChanged -Force
$taskOther = Join-Path $taskFixture 'ModCarrerMode\mods\mascot_single\mascot_goal_line_v26.dll'
$taskBefore = (Get-FileHash -LiteralPath $taskOther).Hash
$taskBackups = @(Get-ChildItem -LiteralPath (Join-Path $taskFixture 'ModCarrerMode\backups')).Count
$taskRejected = $false
try { & (Join-Path $taskPackage 'Install-MatchPresentation.ps1') -GameRoot $taskFixture } catch { $taskRejected=$true }
if (-not $taskRejected -or $taskBefore -ne (Get-FileHash -LiteralPath $taskOther).Hash) { throw 'Conflict protection failed.' }
if (@(Get-ChildItem -LiteralPath (Join-Path $taskFixture 'ModCarrerMode\backups')).Count -ne $taskBackups) { throw 'Conflict copied files before preflight.' }
Write-Output 'PASS: isolated installer, backup and refusal to overwrite a different DLL.'
