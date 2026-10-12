param(
    [Parameter(Mandatory=$true)][string]$Candidate,
    [Parameter(Mandatory=$true)][string]$BackupRoot,
    [switch]$Restore
)
$ErrorActionPreference='Stop'
if (Get-Process fifa16,Server16Python -ErrorAction SilentlyContinue) {
    throw 'Feche o FIFA e o Server16Python antes de substituir o vídeo.'
}
$movie='U:\fifa 16\MoviesGBD\XXX - Caze TV\bootflowoutro.vp8'
$active='U:\fifa 16\data\movies\bootflowoutro.vp8'
$snapshot=Join-Path $BackupRoot 'instalacao_20261006'
$sourceBackup=Join-Path $snapshot 'MoviesGBD-original.vp8'
$activeBackup=Join-Path $snapshot 'data-movies-original.vp8'
if ($Restore) {
    Copy-Item -LiteralPath $sourceBackup -Destination $movie
    Copy-Item -LiteralPath $activeBackup -Destination $active
    Write-Output 'Vídeos originais restaurados; bumper e navegação não foram alterados.'
    exit
}
if (!(Test-Path -LiteralPath $Candidate -PathType Leaf)) { throw 'Candidato ausente.' }
New-Item -ItemType Directory -Path $snapshot -Force | Out-Null
if (!(Test-Path -LiteralPath $sourceBackup)) {
    Copy-Item -LiteralPath $movie -Destination $sourceBackup
}
if (!(Test-Path -LiteralPath $activeBackup)) {
    Copy-Item -LiteralPath $active -Destination $activeBackup
}
$hash=(Get-FileHash -LiteralPath $Candidate).Hash
try {
    Copy-Item -LiteralPath $Candidate -Destination $movie
    Copy-Item -LiteralPath $Candidate -Destination $active
    foreach ($target in @($movie,$active)) {
        if ((Get-FileHash -LiteralPath $target).Hash -ne $hash) { throw 'Hash da instalação divergente.' }
    }
} catch {
    Copy-Item -LiteralPath $sourceBackup -Destination $movie
    Copy-Item -LiteralPath $activeBackup -Destination $active
    throw
}
Write-Output "Candidato instalado na fonte e no destino. SHA256: $hash"
