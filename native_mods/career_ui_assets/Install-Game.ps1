param([string]$GameDirectory='U:\fifa 16')
$ErrorActionPreference='Stop'
$taskRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$taskGame=[IO.Path]::GetFullPath($GameDirectory)
foreach($taskProcess in @(Get-Process FIFA16 -ErrorAction SilentlyContinue)){
    if(-not $taskProcess.Path -or [IO.Path]::GetDirectoryName($taskProcess.Path) -eq $taskGame){throw 'Feche o FIFA normalmente antes de instalar.'}
}
$taskBuilt=Join-Path $PSScriptRoot 'build\career_ui_assets.dll'
$taskTests=Join-Path $PSScriptRoot 'build\test_ui_assets.exe'
$taskKeeperTests=Join-Path $PSScriptRoot 'build\test_keeper_pitch_sheet.exe'
$taskSquadKeeperTests=Join-Path $PSScriptRoot 'build\test_keeper_squad.exe'
$taskFixture=Join-Path $PSScriptRoot 'build\fixture'
if(-not (Test-Path -LiteralPath $taskBuilt) -or -not (Test-Path -LiteralPath $taskTests) -or -not (Test-Path -LiteralPath $taskKeeperTests)){throw 'Execute build.cmd primeiro.'}
& $taskTests $taskFixture
if($LASTEXITCODE -ne 0){throw 'Os testes do carregador falharam.'}
& $taskKeeperTests
if($LASTEXITCODE -ne 0){throw 'Os testes do uniforme de goleiro no campinho falharam.'}
if(-not (Test-Path -LiteralPath $taskSquadKeeperTests)){throw 'Execute build.cmd para gerar o teste do goleiro no Elenco.'}
& $taskSquadKeeperTests
if($LASTEXITCODE -ne 0){throw 'Os testes do uniforme de goleiro na aba Elenco falharam.'}
$taskIcons=Join-Path $taskGame 'data\ui\imgAssets\careerCompetitionIcons'
# Sources and proportional DDS views ship with the package; preserve local edits.
$taskLocalFiles=@()
if(Test-Path -LiteralPath $taskIcons -PathType Container){$taskLocalFiles=@(Get-ChildItem -LiteralPath $taskIcons -Recurse -File -Filter '*.dds')}
$taskPlugin=Join-Path $taskGame 'ModCarrerMode\mods\career_ui_assets\career_ui_assets.dll'
$taskList=Join-Path $taskGame 'ModCarrerMode\mods\enabled.txt'
$taskBackup=Join-Path $taskGame ('ModCarrerMode\backups\calendar_dds_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $taskBackup -Force | Out-Null
Copy-Item -LiteralPath $taskPlugin -Destination (Join-Path $taskBackup 'career_ui_assets.dll')
Copy-Item -LiteralPath $taskList -Destination (Join-Path $taskBackup 'enabled.txt')
$taskPackageDll=Join-Path $taskRepo 'ModCarrerMode\mods\career_ui_assets\career_ui_assets.dll'
if($taskPackageDll -ne $taskPlugin -and (Test-Path -LiteralPath $taskPackageDll)){
    Copy-Item -LiteralPath $taskPackageDll -Destination (Join-Path $taskBackup 'package-career_ui_assets.dll')
}
$taskBefore=@{}
foreach($taskRelative in @('dinput8.dll')){
    $taskBefore[$taskRelative]=(Get-FileHash -LiteralPath (Join-Path $taskGame $taskRelative)).Hash
}
Copy-Item -LiteralPath $taskBuilt -Destination $taskPackageDll -Force
Copy-Item -LiteralPath $taskBuilt -Destination $taskPlugin -Force
if((Get-FileHash -LiteralPath $taskBuilt).Hash -ne (Get-FileHash -LiteralPath $taskPlugin).Hash){throw 'Hash da DLL diferente.'}
$taskLibrary=Join-Path $taskRepo 'data\ui\imgAssets\careerCompetitionIcons'
foreach($taskImage in Get-ChildItem -LiteralPath $taskLibrary -File -Filter '*.png') {
    $taskId=$taskImage.BaseName
    if($taskId -notmatch '^\d+$'){continue}
    $taskDestination=Join-Path $taskIcons $taskImage.Name
    if((Test-Path -LiteralPath $taskDestination) -and (Get-FileHash -LiteralPath $taskDestination).Hash -ne (Get-FileHash -LiteralPath $taskImage.FullName).Hash){continue}
    foreach($taskRelative in @($taskImage.Name,('calendar\c'+$taskId+'.dds'),('cards\c'+$taskId+'.dds'))) {
        $taskDestination=Join-Path $taskIcons $taskRelative
        New-Item -ItemType Directory -Force -Path (Split-Path $taskDestination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $taskLibrary $taskRelative) -Destination $taskDestination -Force
    }
}
foreach($taskRelative in @('competitions.tsv','calendar\empty.dds','cards\empty.dds')) {
    $taskDestination=Join-Path $taskIcons $taskRelative
    New-Item -ItemType Directory -Force -Path (Split-Path $taskDestination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $taskLibrary $taskRelative) -Destination $taskDestination -Force
}
$taskText=[IO.File]::ReadAllText($taskList)
if($taskText -notmatch '(?m)^career_ui_assets\\career_ui_assets\.dll\s*$'){
    [IO.File]::AppendAllText($taskList,"`r`n# Dedicated career calendar DDS icons.`r`ncareer_ui_assets\career_ui_assets.dll`r`n",[Text.UTF8Encoding]::new($false))
}
foreach($taskRelative in $taskBefore.Keys){
    if($taskBefore[$taskRelative] -ne (Get-FileHash -LiteralPath (Join-Path $taskGame $taskRelative)).Hash){throw "Arquivo externo alterado: $taskRelative"}
}
$taskRestore=@'
param([string]$GameDirectory='U:\fifa 16')
$ErrorActionPreference='Stop'
if(Get-Process FIFA16 -ErrorAction SilentlyContinue){throw 'Feche o FIFA normalmente antes de restaurar.'}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'career_ui_assets.dll') -Destination (Join-Path $GameDirectory 'ModCarrerMode\mods\career_ui_assets\career_ui_assets.dll') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'enabled.txt') -Destination (Join-Path $GameDirectory 'ModCarrerMode\mods\enabled.txt') -Force
Write-Output 'Modulo anterior restaurado. Os DDS da pasta nova foram preservados.'
'@
[IO.File]::WriteAllText((Join-Path $taskBackup 'Restore-CalendarDds.ps1'),$taskRestore,[Text.UTF8Encoding]::new($false))
$taskResult=@{
    game=$taskGame; directory=$taskIcons; dds_count=$taskLocalFiles.Count;
    dll_sha256=(Get-FileHash -LiteralPath $taskPlugin).Hash; backup=$taskBackup; unchanged=$taskBefore;
    visual_validation='pending next game launch'
}
$taskResult | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $taskBackup 'installation.json') -Encoding utf8
$taskResult | ConvertTo-Json -Depth 3
