$ErrorActionPreference='Stop'
$base=Join-Path $PSScriptRoot 'build\fixture\data\ui\imgAssets\careerCompetitionIcons'
foreach($kind in @('calendar','cards')) {
    $folder=Join-Path $base $kind
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $side=if($kind -eq 'calendar'){128}else{256}
    $dds=New-Object byte[] (128+$side*$side)
    [Text.Encoding]::ASCII.GetBytes('DDS ').CopyTo($dds,0)
    foreach($field in @(@(4,124),@(12,$side),@(16,$side),@(76,32),@(80,4),@(108,0x1000))){[BitConverter]::GetBytes([uint32]$field[1]).CopyTo($dds,[int]$field[0])}
    [Text.Encoding]::ASCII.GetBytes('DXT5').CopyTo($dds,84)
    foreach($id in @(1761,1620,1460,2442,2240)){[IO.File]::WriteAllBytes((Join-Path $folder ('c'+$id+'.dds')),$dds)}
    [IO.File]::WriteAllBytes((Join-Path $folder 'empty.dds'),$dds)
}
[IO.File]::WriteAllText((Join-Path $base 'competitions.tsv'),"competition_id`tvisual_id`tlabel`n1761`t7`tBrasileirao`n1620`t229`tCopa do Brasil`n1460`t1003`tLibertadores`n2442`t23`tCarioca`n2240`t820`tPreseason`n")
