[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$GameRoot,[switch]$VerifyOnly)
$ErrorActionPreference='Stop'
$game=(Resolve-Path -LiteralPath $GameRoot).Path.TrimEnd('\')
$baselines=@(
    @{Path='data\ui\game\components\careercomponents\careerhubwidget.big';Name='careerhubwidget.big';Hash='9fb40d261e9d04033d9e606507a7c1dc88f5ca6c0107e6cd4350e38e77707260'},
    @{Path='data\ui\pow\components\easfcwidget.big';Name='easfcwidget.big';Hash='192ef034f327914c055779e0163c5ddecfc1247b28d47a261a752e9b150dbf28'},
    @{Path='data\ui\game\widgets\mainhubwidget.big';Name='mainhubwidget.big';Hash='ce6974096b1a5a1fa3ccd1b26a9312f965256ec476fa0ffbafab7804bc81cca3'}
)
foreach($item in $baselines) {
    $item.Source=Join-Path $PSScriptRoot ('originals\'+$item.Name)
    if ((Get-FileHash -LiteralPath $item.Source -Algorithm SHA256).Hash -ne $item.Hash) { throw "Original divergente: $($item.Name)" }
    $item.Target=Join-Path $game $item.Path
    $item.Before=$(if(Test-Path -LiteralPath $item.Target -PathType Leaf) {(Get-FileHash -LiteralPath $item.Target).Hash} else {$null})
}
$changes=@($baselines | Where-Object {$_.Before -ne $_.Hash})
if ($VerifyOnly) {
    [pscustomobject]@{Disabled=($changes.Count -eq 0);ToRestore=$changes.Count;Game=$game}
    return
}
$backup=$null
if ($changes.Count) {
    # These copies stay outside every active UI path; the implementation and
    # the user's current BIGs remain available for a later diagnostic.
    $backup=Join-Path $game ('ModCarrerMode\disabled\career_branding\'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach($item in $changes) {
        if ($item.Before) {
            $saved=Join-Path $backup $item.Path
            New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($saved)) | Out-Null
            Copy-Item -LiteralPath $item.Target -Destination $saved
            if ((Get-FileHash -LiteralPath $saved).Hash -ne $item.Before) { throw 'Backup de interface divergente.' }
        }
    }
    $baselines | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'before.json') -Encoding utf8
    foreach($item in $changes) {
        New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($item.Target)) | Out-Null
        $temporary=$item.Target+'.disable-branding-'+[guid]::NewGuid().ToString('N')+'.tmp'
        Copy-Item -LiteralPath $item.Source -Destination $temporary
        if ((Get-FileHash -LiteralPath $temporary).Hash -ne $item.Hash) { throw 'Copia da interface original divergente.' }
        if (Test-Path -LiteralPath $item.Target) {
            $replaced=Join-Path $backup ('replaced\'+$item.Path)
            New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($replaced)) | Out-Null
            [IO.File]::Replace($temporary,$item.Target,$replaced)
        }
        else {[IO.File]::Move($temporary,$item.Target)}
        if ((Get-FileHash -LiteralPath $item.Target).Hash -ne $item.Hash) { throw 'Restauracao de interface divergente.' }
    }
}
[pscustomobject]@{Disabled=$true;Restored=$changes.Count;PreservedModifiedFiles=$backup;RestartFifaRequired=($changes.Count -gt 0);Game=$game}
