param(
    [Parameter(Mandatory=$true)][string]$GameRoot,
    [switch]$IncludeServer
)
$ErrorActionPreference = 'Stop'
$taskGame = (Resolve-Path -LiteralPath $GameRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $taskGame 'fifa16.exe'))) {
    throw 'Escolha a raiz do FIFA 16, onde está fifa16.exe.'
}
if (Get-Process -Name fifa16 -ErrorAction SilentlyContinue) {
    throw 'Feche o FIFA antes de instalar as DLLs. Nenhum arquivo foi alterado.'
}
if ($IncludeServer -and (Get-Process -Name Server16Python -ErrorAction SilentlyContinue)) {
    throw 'Feche o Server16Python antes de substituir o EXE.'
}
$taskManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$taskItems = @($taskManifest.files)
if (-not $IncludeServer) { $taskItems = @($taskItems | Where-Object { $_.kind -eq 'mod' }) }
$taskPlan = @()
foreach ($taskItem in $taskItems) {
    $taskSource = Join-Path $PSScriptRoot $taskItem.relative
    $taskTarget = Join-Path $taskGame $taskItem.relative
    $taskResolvedTarget = [IO.Path]::GetFullPath($taskTarget)
    if (-not $taskResolvedTarget.StartsWith($taskGame.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Destino fora da pasta selecionada.'
    }
    if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash -ne $taskItem.sha256) {
        throw 'Pacote alterado ou incompleto. Não foi instalado.'
    }
    if (-not (Test-Path -LiteralPath $taskTarget) -and $taskItem.kind -eq 'mod') {
        throw "Mod não instalado nesse jogo: $($taskItem.relative). Não se altera o carregador automaticamente."
    }
    if (Test-Path -LiteralPath $taskTarget) {
        $taskOldHash = (Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash
        if ($taskItem.kind -eq 'mod' -and $taskOldHash -ne $taskItem.original_sha256 -and $taskOldHash -ne $taskItem.sha256) {
            throw "Existe uma revisão diferente de $($taskItem.relative). Integre os switches ao fonte novo; não sobrescreva essa DLL. Nenhum arquivo foi alterado."
        }
    }
    $taskPlan += [PSCustomObject]@{ Source=$taskSource; Target=$taskTarget; Relative=$taskItem.relative; Hash=$taskItem.sha256; Existed=(Test-Path -LiteralPath $taskTarget) }
}
$taskBackup = Join-Path $taskGame ('ModCarrerMode\backups\match_presentation_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $taskBackup | Out-Null
foreach ($taskStep in $taskPlan) {
    if ($taskStep.Existed) {
        $taskBackupFile = Join-Path $taskBackup $taskStep.Relative
        New-Item -ItemType Directory -Path (Split-Path $taskBackupFile -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $taskStep.Target -Destination $taskBackupFile
    }
}
$taskApplied = @()
try {
    foreach ($taskStep in $taskPlan) {
        $taskApplied += $taskStep
        Copy-Item -LiteralPath $taskStep.Source -Destination $taskStep.Target -Force
        if ((Get-FileHash -LiteralPath $taskStep.Target -Algorithm SHA256).Hash -ne $taskStep.Hash) {
            throw 'Verificação após a cópia falhou.'
        }
    }
} catch {
    foreach ($taskStep in $taskApplied) {
        if ($taskStep.Existed) {
            Copy-Item -LiteralPath (Join-Path $taskBackup $taskStep.Relative) -Destination $taskStep.Target -Force
        } elseif (Test-Path -LiteralPath $taskStep.Target) {
            Remove-Item -LiteralPath $taskStep.Target
        }
    }
    throw
}
Write-Host 'DLLs compatíveis instaladas. As regras do carregador, assets e público não foram alteradas.'
Write-Host "Backup: $taskBackup"
Write-Host 'Abra o FIFA e o Server novamente. Aplicar no painel cria ou atualiza somente match_presentation.ini.'
