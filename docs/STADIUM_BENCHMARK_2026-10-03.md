# Maracanã/Flamengo: interface e desempenho

## O que entrou na build

Foco com contorno azul forte, quatro pixels lógicos (oito na textura 2x), mais
separação branca para manter contraste sobre fotografias e botões azuis.
Aplicar com foco fica azul-escuro e exibe uma legenda explícita de confirmação.
Pesquisa, países, teclado virtual e controles de áudio usam o mesmo padrão.
Mover o mouse muda somente o foco: não aplica estádio, não troca país, não
digita nem ajusta volume. Um cursor parado não substitui a seleção do joystick.
Passar por pontos do mesmo alvo não gera novas imagens desnecessariamente.

As prioridades, cópias de aplicação, offsets de memória e lógica de
estádio/vídeo/placar não foram alterados pelo ajuste de interface. Na rodada
inicial os protótipos abaixo não entraram na build. Depois da autorização,
a publicação RAR por renomeação foi implementada com validação e fallback;
a comparação da implementação final está ao fim deste documento.

## Método e limites

Teste em 03/10/2026, Windows 11 Home build 26200, Python 3.10.11 x64.
Origem: `E:\games\fifa friends\StadiumGBD\BRA - Maracana - Flamengo.rar`.
É um RAR de 128.214.651 bytes; contém 21 arquivos, somando 623.263.079 bytes.
As texturas de dia e noite têm 300.345.142 bytes cada: juntas são 96,4% do total.

O teste usou uma pasta única `E:\cgfs16_benchmark_p_4y9yax`, fora do jogo, no
mesmo volume E (NTFS, X12 SSD 1TB, conectado por USB). A pasta foi removida ao
terminar. Os arquivos originais do jogo foram somente lidos; U não foi usado.
Baselines dos slots 176/261 foram copiados para a árvore de jogo simulada
antes de cada medição. O worker real aplicou os assets nessa árvore, sem FIFA,
injeção, alterações de memória, navegação, vídeos ou configurações instaladas.
O teste comparou SHA256 de todos os arquivos de saída das variantes com a
saída do fluxo atual; as comparações passaram.

UnRAR atual, protótipo de renomeação e reutilização da pasta extraída tiveram
três repetições; `tar` e cada ZIP tiveram uma. O cache do Windows não foi
esvaziado. A ordem dos grupos não foi intercalada: há efeitos de cache, fila
de gravação e disco. O disco E apresentou variação grande de I/O durante a
rotina. Os tempos são observações desta máquina, não uma promessa de ganho.

O cleanup temporário do worker foi desabilitado no teste para comparar os
bytes extraídos; a limpeza da sandbox ocorreu depois, fora dos tempos. O
total simulado não inclui preparação do baseline, hashes de comparação,
inicialização do EXE, writes de memória nem uma partida concorrente.

Dados completos: `build/benchmarks/maracana-20261003.json`.

## Extração e aplicação

Medianas e intervalos das execuções, em segundos:

| Caminho | Extração completa | Worker completo simulado |
| --- | ---: | ---: |
| Atual, UnRAR + CRC + cópia temporária | 12,26 (9,89–12,86) | 33,71 (27,20–48,23) |
| Protótipo, UnRAR + CRC + renomeação | 12,82 (10,00–16,06) | 18,81 (14,54–21,12) |
| `tar` + CRC + cópia temporária, uma execução | 74,01 | 78,87 |
| Pasta previamente extraída, sem extrair de novo | não se aplica | 59,36 (9,46–88,76) |

No caminho atual, o processo UnRAR isolado levou 4,84–9,57 s; a conferência
de tamanho/CRC levou 0,45–0,47 s. A publicação entre duas pastas temporárias
releu e regravou os 623 MB, consumindo 2,77–6,53 s (mediana 4,53 s).

No protótipo, o conteúdo foi validado da mesma forma e a pasta nova foi
renomeada, no mesmo volume, em 0,00068–0,00077 s. É uma redução demonstrada
nessa etapa específica. A descompactação total não melhorou na mediana, e a
diferença entre os totais de aplicação não pode ser atribuída só à renomeação
devido à oscilação de I/O e à ordem dos grupos. O cache também não mostrou
um ganho consistente neste teste; requer medição controlada adicional.

## Criar e extrair ZIP

ZIPs foram criados somente na sandbox com os mesmos 21 arquivos, depois
extraídos pelo código atual e comparados byte a byte por hashes. Não houve
conversão/substituição do RAR instalado. Valores de uma execução por formato:

| Formato | Tamanho decimal | Criar ZIP | Extrair ZIP |
| --- | ---: | ---: | ---: |
| ZIP sem compressão (`STORED`) | 623,27 MB | 80,67 s | 2,76 s |
| ZIP Deflate nível 1 | 200,79 MB | 11,17 s | 4,68 s |
| RAR original, referência de tamanho | 128,21 MB | não medido | 12,26 s, mediana do fluxo completo de extração atual |

O ZIP Deflate nível 1 ficou 56,6% maior que o RAR. Esta é apenas uma medição
histórica: conforme solicitado, o pacote comprimido existente não será
alterado, convertido ou recomprimido pela melhoria.
Os tempos de ZIP são apenas extração, não aplicação no jogo, e variam com
compressão, disco e caches. O tempo alto para criar o ZIP sem compressão
reforça a necessidade de controlar I/O antes de concluir sobre performance.

## Propostas da rodada inicial

1. **Eliminar a cópia temporária redundante de RAR validado.** Manter a
   extração completa, validação de caminhos, arquivos, tamanho e CRC. Quando
   o destino for uma pasta temporária nova e vazia no mesmo volume, publicar
   por renomeação. Destinos existentes, bloqueios ou volumes diferentes
   devem manter um fallback seguro. O Windows tem restrições diferentes
   para mover arquivos e diretórios entre volumes; não se deve transformar
   indiscriminadamente toda cópia em move. [Documentação Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw).
2. **Manter UnRAR como primeira opção disponível e preservar os fallbacks.**
   O `tar` funcionou para o RAR real neste teste, mas foi significativamente
   mais lento. Não selecionar o backend apenas pelo nome da extensão nem
   pressupor que `tar` exista em toda instalação do Windows.
3. **Avaliar cache limitado de extração validada.** Invalidar quando o pacote
   mudar; conferir integridade, limitar espaço e permitir limpar. Nunca
   compartilhar assets mutáveis do jogo com o cache por hardlinks. Pré-carga
   em background deve escrever apenas no cache, não aplicar assets nem
   alterar navegação/vídeos. Não há ganho de tempo consistente comprovado
   para essa proposta nesta rodada.
4. **Instrumentar e repetir em ordem intercalada.** Separar restauração do
   baseline, cópias de modelos/texturas, extras e cleanup; repetir sem carga
   concorrente no disco. Preservar a sequência original da aplicação, sem
   cópias paralelas sobre os mesmos slots. Dois arquivos concentram quase
   todo o volume de dados: reduzir I/O redundante merece prioridade.
5. **Conversão/recompressão fora do escopo.** A comparação de ZIP acima foi
   apenas experimental; o usuário confirmou que o arquivo comprimido não
   pode mudar. Nenhuma mudança de formato entrou na implementação.

## Compatibilidade e verificação

Passaram 60 testes Python na rodada inicial, incluindo ZIP STORED/Deflate, ZIP64, acentos,
espaços, pastas vazias, CRC inválido, método não suportado, ZIP marcado como
criptografado, caminhos absolutos/UNC/traversal, RAR incompleto, fallback e
timeout. Erros de criptografia/método não suportado são rejeições explícitas,
não suporte a esses formatos. Os testes nativos de canal/entrada e renderer
D3D11 isolado também passaram. O teste nativo cobre a regra de movimento do
cursor sem enviar input ao jogo; não substitui teste com joystick real.

Não foi testada uma partida nem uma matriz de versões do Windows. A base
Python 3.10 é documentada para Windows 8.1 e posteriores; não é correto
prometer esta build em qualquer Windows, principalmente Windows 7.
Isso é o mínimo do interpretador, não uma certificação de todas as demais
dependências. [Python no Windows](https://docs.python.org/3.10/using/windows.html).

## Repetir a rotina

Na raiz do projeto, usando o Python da build:

```powershell
& 'C:\Users\igorv\AppData\Local\Programs\Python\Python310\python.exe' scripts/benchmark_stadium.py 'E:\games\fifa friends\StadiumGBD\BRA - Maracana - Flamengo.rar' --scratch-parent 'E:\' --baseline 'E:\games\fifa friends\FSW' --output 'build\benchmarks\maracana-20261003.json' --repeats 3
```

A rotina exige pelo menos 4 GiB livres para gerar os ZIPs e árvores
temporárias, não instala ferramentas e não roda o FIFA. Os protótipos só
operam em pastas novas criadas por ela; a instalação é origem de leitura.

## Implementação final: publicação RAR validada com fallback

O worker agora habilita `fast_publish=True` exclusivamente para sua pasta
temporária de extração. A pasta precisa continuar vazia, manter a identidade
capturada antes da extração, não ser link/reparse point e estar no mesmo
volume da staging. A verificação de tamanho e CRC ocorre antes de publicar.
Links, arquivos incompletos e CRC inválido são rejeitados em ambos os caminhos.

Depois da validação, apenas a pasta temporária vazia é removida e a staging
é renomeada para esse destino. Se remover/renomear não for possível, se a
identidade mudar ou se a pasta receber outros arquivos, o caminho de cópia
anterior é usado. Não se repete a descompactação nem se ignora a validação.
Se a própria cópia também falhar, o worker informa erro e não inicia a
aplicação do pacote. A limpeza de temporários permanece no `finally`.
Outros chamadores mantêm o comportamento de cópia por padrão.

Nova medição do mesmo RAR real, com três pares em ordem alternada entre
cópia e renomeação, no volume E. Tempos excluem hashes e limpeza; incluem
descompactação, validação e publicação, mas não aplicação no jogo:

| Etapa, mediana | Cópia anterior | Renomeação validada |
| --- | ---: | ---: |
| Extração completa | 9,17 s | 6,88 s |
| Validação de tamanho/CRC | 0,489 s | 0,477 s |
| Publicação temporária | 3,038 s | 0,00123 s |

Ganho medido na extração completa: **2,29 s, aproximadamente 25%**. Os
totais variaram entre 8,85–18,95 s na cópia e 5,26–10,15 s na renomeação.
O cache do Windows não foi esvaziado; o resultado não é garantia de ganho
em outras máquinas, volumes ou partidas concorrentes.

Também foi forçado um `PermissionError` na renomeação do pacote real. A
cópia antiga assumiu, terminou em 8,06 s e produziu a mesma árvore por SHA256,
sem extrair novamente. Todas as saídas dos sete ensaios foram idênticas.
O hash do RAR foi conferido antes/depois e não mudou. A sandbox
`E:\cgfs16_rar_compare_zg6mrx27` foi removida; nenhum arquivo instalado no FIFA
foi escrito. U não foi usado neste teste.

Passaram **74 testes Python**, incluindo destino trocado/vazio, destino
preenchido durante extração, diretório bloqueado, falta de identidade
estável, erros de renomeação, falha da cópia, CRC inválido e integração do
worker em jogo simulado. Ainda é necessário testar uma partida no FIFA real.

Dados: `build/benchmarks/maracana-fast-publication-20261003.json`.
Rotina final, sem gerar ZIPs nem alterar o arquivo comprimido:

```powershell
& 'C:\Users\igorv\AppData\Local\Programs\Python\Python310\python.exe' scripts/benchmark_rar_publication.py 'E:\games\fifa friends\StadiumGBD\BRA - Maracana - Flamengo.rar' --scratch-parent 'E:\' --output 'build\benchmarks\maracana-fast-publication-20261003.json' --repeats 3
```
