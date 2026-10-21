[CmdletBinding()]
param(
    [string]$GameDirectory = 'U:\fifa 16',
    [string]$BackupDirectory,
    [string]$PayloadPath,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
# FIFA's BH index must release this path before the loose APT can be loaded.
# Never distribute a complete BH: other installations have different indexes.
if (-not ('FifaFriends.BirthyearUiIndex' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
namespace FifaFriends {
    public sealed class BirthyearUiPlan {
        public string Archive, Index, BeforeSha256, AfterSha256;
        public int Entry, HashOffset;
        public bool NeedsActivation;
    }
    public static class BirthyearUiIndex {
        const string Target = "data/ui/game/screens/virtualpro/vpro_proinfo.big";
        static uint BE(byte[] b, int p) {
            return ((uint)b[p] << 24) | ((uint)b[p+1] << 16) | ((uint)b[p+2] << 8) | b[p+3];
        }
        static string Sha(byte[] b) {
            using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(b)).Replace("-", "");
        }
        static byte[] Read(Stream s, int count) {
            var b = new byte[count]; int at = 0, n;
            while (at < count && (n = s.Read(b, at, count-at)) > 0) at += n;
            if (at != count) throw new InvalidDataException("Arquivo truncado.");
            return b;
        }
        public static BirthyearUiPlan[] Plan(string game) {
            var plans = new List<BirthyearUiPlan>(); int archives = 0;
            foreach (string stem in new[]{"data_front_end_extra", "data_front_end", "data_patch", "data_startup"}) {
                string big = Path.Combine(game, stem+".big");
                if (!File.Exists(big)) continue;
                archives++;
                using (var s = File.OpenRead(big)) {
                    byte[] h = Read(s,16);
                    string magic = Encoding.ASCII.GetString(h,0,4);
                    if (magic != "BIG4" && magic != "BIGF") throw new InvalidDataException("BIG desconhecido: "+big);
                    uint count = BE(h,8), end = BE(h,12);
                    if (count > 1000000 || end < 16 || end > 134217728 || end > s.Length)
                        throw new InvalidDataException("Diretorio BIG invalido: "+big);
                    byte[] table = Read(s,(int)end-16);
                    var offsets = new uint[count]; var sizes = new uint[count];
                    int p = 0, match = -1;
                    for (int i=0; i<count; i++) {
                        if (p+8 >= table.Length) throw new InvalidDataException("Diretorio BIG truncado: "+big);
                        offsets[i] = BE(table,p); sizes[i] = BE(table,p+4);
                        int z = Array.IndexOf(table,(byte)0,p+8);
                        if (z < 0) throw new InvalidDataException("Nome BIG sem terminador: "+big);
                        string name = Encoding.ASCII.GetString(table,p+8,z-p-8).Replace('\\','/');
                        if (String.Equals(name,Target,StringComparison.OrdinalIgnoreCase)) {
                            if (match >= 0) throw new InvalidDataException("Entrada de nascimento duplicada: "+big);
                            match = i;
                        }
                        p = z+1;
                    }
                    if (match < 0) continue;
                    string bh = Path.ChangeExtension(big,".bh");
                    byte[] index = File.ReadAllBytes(bh);
                    long expected = 16L+20L*count;
                    if (index.Length != expected || Encoding.ASCII.GetString(index,0,4) != "ViV4" ||
                        BitConverter.ToUInt32(index,4) != expected || BE(index,8) != count || BE(index,12) != expected)
                        throw new InvalidDataException("BH desconhecido ou incompativel: "+bh);
                    // Validate ordering against every BIG directory record, not a fixed retail index.
                    for (int i=0; i<count; i++) {
                        int at = 16+20*i;
                        if (BE(index,at) != offsets[i] || BE(index,at+4) != sizes[i] ||
                            (long)offsets[i]+sizes[i] > s.Length)
                            throw new InvalidDataException("BH nao corresponde ao BIG: "+bh+" entrada "+i);
                    }
                    int hash = 16+20*match+12; byte[] after = (byte[])index.Clone();
                    bool needed = false;
                    for (int i=0; i<8; i++) { needed |= index[hash+i] != 0; after[hash+i] = 0; }
                    plans.Add(new BirthyearUiPlan { Archive=big, Index=bh, Entry=match, HashOffset=hash,
                        BeforeSha256=Sha(index), AfterSha256=Sha(after), NeedsActivation=needed });
                }
            }
            if (archives > 0 && plans.Count == 0) throw new InvalidDataException("Interface de nascimento nao encontrada nos BIGs desta instalacao.");
            return plans.ToArray();
        }
        public static void Apply(BirthyearUiPlan plan, string backup) {
            if (!plan.NeedsActivation) return;
            // Exclusive open plus compare prevents overwriting a concurrent regeneration.
            using (var s = new FileStream(plan.Index,FileMode.Open,FileAccess.ReadWrite,FileShare.None)) {
                byte[] before = Read(s,(int)s.Length);
                if (Sha(before) != plan.BeforeSha256) throw new IOException("BH mudou durante a preparacao: "+plan.Index);
                using (var saved = new FileStream(backup,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
                    saved.Write(before,0,before.Length); saved.Flush(true);
                }
                if (Sha(File.ReadAllBytes(backup)) != plan.BeforeSha256) throw new IOException("Backup BH divergente.");
                try {
                    s.Position = plan.HashOffset; s.Write(new byte[8],0,8); s.Flush(true);
                    s.Position = 0;
                    if (Sha(Read(s,before.Length)) != plan.AfterSha256) throw new IOException("Verificacao BH divergente.");
                } catch {
                    s.Position = plan.HashOffset; s.Write(before,plan.HashOffset,8); s.Flush(true);
                    throw;
                }
            }
        }
    }
}
'@
}
$game = (Resolve-Path -LiteralPath $GameDirectory).Path
if (-not $PayloadPath) { $PayloadPath = Join-Path $game 'data\ui\game\screens\virtualpro\vpro_proinfo.big' }
$payloadHash = (Get-FileHash -LiteralPath $PayloadPath -Algorithm SHA256).Hash
if ($payloadHash -ne 'B5CFF1DF25EAFE1453E11589CFD39675463DB3A63F80371C967CB47F88B342CE') {
    throw 'Instale primeiro o payload validado vpro_proinfo.big (2006-2012).'
}
$plans = @([FifaFriends.BirthyearUiIndex]::Plan($game))
$pending = @($plans | Where-Object NeedsActivation)
$backup = $null
if (-not $VerifyOnly -and $pending.Count) {
    if (-not $BackupDirectory) { $BackupDirectory = Join-Path $game 'ModCarrerMode\backups' }
    $backup = Join-Path ([IO.Path]::GetFullPath($BackupDirectory)) ('birthyear_ui_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach ($plan in $pending) {
        [FifaFriends.BirthyearUiIndex]::Apply($plan,(Join-Path $backup ([IO.Path]::GetFileName($plan.Index))))
    }
    $plans | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'activation.json') -Encoding utf8
}
[pscustomobject]@{
    Status = $(if (-not $plans.Count) {'BaseArchivesAbsent'} elseif ($VerifyOnly -and $pending.Count) {'ActivationRequired'} else {'LooseInterfaceActive'})
    Indexes = $plans.Count
    Changed = $(if ($VerifyOnly) {0} else {$pending.Count})
    Pending = $(if ($VerifyOnly) {$pending.Count} else {0})
    RestartRequired = (-not $VerifyOnly -and $pending.Count -gt 0)
    Backup = $backup
    Entries = $plans
}
