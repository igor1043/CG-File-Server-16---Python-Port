# CGFS 16 Server 16 Python Port

Python conversion of the original CGFS 16 Server 16 tool for FIFA 16.

This project is a community-friendly, public rewrite of the classic FIFA 16 Server 16 workflow. It provides a Windows desktop control panel and in-game overlay for managing stadium assignments, scoreboards, TV logos, movies, chants, and camera packages while FIFA 16 is running.

## What This Project Does

- Converts the legacy Server 16 behavior into Python.
- Attaches to FIFA 16 memory to read live match context.
- Applies stadium, scoreboard, TV logo, movie, chants, and camera logic based on the current match state.
- Loads assigned stadiums from normal folders or `.zip` / `.rar` archives.
- Supports an overlay-style main UI that can appear on top of FIFA 16.
- Opens secondary editors and assignment dialogs as floating windows outside the overlay flow.
- Includes tools for editing `settings.ini`-driven assignment data.
- Packages the project as a standalone Windows executable with PyInstaller.

## Project Status

This repository is intended to be public and open for community contributions.

The goal is to preserve and evolve the FIFA 16 Server 16 experience in a modern Python codebase that is easier to maintain, improve, and extend.

For a simple user-oriented explanation of the FIFA Friends version, see
[docs/ROTEIRO_FIFA_FRIENDS.md](docs/ROTEIRO_FIFA_FRIENDS.md).

## Screenshots


Main overlay:

<img width="1007" height="667" alt="Screenshot_2" src="https://github.com/user-attachments/assets/9b533e22-21c2-46e2-adc0-a40a71e3ec3a" />

<img width="1008" height="694" alt="Screenshot_1" src="https://github.com/user-attachments/assets/ed0296f2-a270-48c0-a0cf-91d90054891c" />

<img width="1010" height="698" alt="Screenshot_3" src="https://github.com/user-attachments/assets/c3a08a83-bef0-4dd4-a445-336ea80be6ea" />


These paths are reserved so contributors can add screenshots later without changing the documentation structure.

## Repository Structure

- `main.py`: project entry point.
- `server16_py/`: main application source code.
- `server16_py/app.py`: primary UI, overlay management, and runtime coordination.
- `server16_py/assignment_runtime.py`: assignment flow for stadiums, scoreboards, TV logos, movies, and exclusions.
- `server16_py/stadium_runtime.py`: stadium loading and application logic, including folder and archive sources.
- `server16_py/asset_runtime.py`: scoreboard, TV logo, movie, and related routing.
- `server16_py/chants_runtime.py`: chants and audio playback runtime.
- `server16_py/camera_runtime.py`: Anth camera package discovery, preview, and application.
- `server16_py/settings_editor.py`: settings editing UI.
- `server16_py/dialogs.py`: assignment dialogs.
- `server16_py/file_tools.py`: shared file-copying, archive extraction, and setup helpers.
- `runtime/`: local runtime data such as settings and logs.
- `legacy/`: reference material from the original project/conversion process.
- `build_exe.bat`: convenience build script for Windows.
- `Server16Python.spec`: PyInstaller spec file.

## Requirements

- Windows
- FIFA 16 installed locally
- Python 3.10+ recommended
- The Python packages used by the project, especially:
  - `psutil`
  - `Pillow`
  - `pygame`
  - `rarfile` for native RAR extraction when available
  - `pyinstaller` for packaging

RAR stadium archives can also be extracted through the Windows `tar` command when `rarfile` is not installed. Depending on your environment, additional packages may be needed if they are introduced by future changes.

## Running From Source

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install the dependencies you need.
4. Run the app with Python.

Example:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install psutil pillow pygame rarfile pyinstaller
python main.py
```

## First-Time Setup

When the tool opens:

1. Point it to your `FIFA 16.exe` if needed.
2. Let it detect the game folder and related `FSW`, `StadiumGBD`, `ScoreBoardGBD`, `TVLogoGBD`, `MoviesGBD`, and other data folders.
3. Start FIFA 16.
4. Use the tool in normal window mode or arm the overlay mode.

The application stores local settings in `runtime/settings.json` and reads/writes Server 16 assignment data from `FSW/settings.ini` inside the detected FIFA 16 folder.

## Expected FIFA Folder Layout

The runtime resolves mod folders from the selected `FIFA 16.exe` directory:

```text
FIFA 16/
  FSW/
    settings.ini
    stadium/
    ScoreBoard/
    TVLogo/
    Nav/
    Chants/
    Images/
      PitchMowPattern/
      Nets/
      Police/
  StadiumGBD/
    render/
      thumbnail/
        stadium/
  ScoreBoardGBD/
  TVLogoGBD/
  MoviesGBD/
```

For pitch, net, and police assets, the current code supports both the root `FSW` folders and the older `FSW/Images` folders:

```text
FSW/PitchMowPattern/
FSW/Nets/
FSW/Police/

FSW/Images/PitchMowPattern/
FSW/Images/Nets/
FSW/Images/Police/
```

Runtime bootstrap copying prefers the root `FSW/PitchMowPattern`, `FSW/Nets`, and `FSW/Police` folders when they exist. The stadium assignment dialog uses the `FSW/Images/...` folders first for selector values and preview PNGs, then falls back to the root folders.

## Stadium Preview Images

The project supports optional preview images for stadiums.

When present, these images are shown in:

- the dashboard `Stadium Bay`
- the `Assign Stadium` window under `Visual Details`
- the `Loading Stadium` modal during stadium application

To be detected correctly, stadium preview images now live in one shared thumbnail folder:

```text
StadiumGBD/render/thumbnail/stadium/
```

Each preview file must use the stadium name as its file name. If the stadium is loaded from a `.zip` or `.rar`, use the archive stem.

```text
StadiumGBD/render/thumbnail/stadium/<stadium name>.png
StadiumGBD/render/thumbnail/stadium/<stadium name>.jpg
StadiumGBD/render/thumbnail/stadium/<stadium name>.jpeg
```

Example:

```text
StadiumGBD/ARG - Diego Armando Maradona.zip
StadiumGBD/render/thumbnail/stadium/ARG - Diego Armando Maradona.jpg
```

Notes:

- The preview file stem must exactly match the stadium folder name or archive stem used by the assignment.
- Supported preview extensions are `.png`, `.jpg`, `.jpeg`, and `.jepg`.
- The app also uses this folder when discovering stadium names for the assignment and settings editors, alongside normal stadium folders and `.zip` / `.rar` files in `StadiumGBD`.
- The old per-stadium layouts `StadiumGBD/<stadium name>/render/thumbnail/stadium.*` and `StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.*` are no longer used by the current code.
- If no preview image exists, the stadium still works normally; the preview area is simply hidden where applicable.
- This structure is intended to make community stadium packs easy to organize and share.

## Stadium Folder And Archive Loading

Stadium assignments are read from `FSW/settings.ini`. A stadium value can point to:

```text
StadiumGBD/<stadium name>/
StadiumGBD/<stadium name>.zip
StadiumGBD/<stadium name>.rar
```

When an assignment points to an archive, the app extracts it into a temporary folder under `runtime/`, finds the first valid stadium folder inside it, applies the stadium files, and then cleans up the temporary extraction.

Valid stadium folders are expected to include normal Server 16 stadium files such as:

```text
model.rx3
texture_day.rx3
texture_night.rx3
crowd_day.dat
crowd_night.dat
EntranceScene/
1/
3/
```

Optional files supported by the runtime:

- `NoSeats.rx3` for crowd-chair replacement.
- `StadiumMovie.vp8` and `StadiumBumper.big` for stadium-specific movies.

Archive extraction is used only for loading the stadium files. Preview lookup does not extract archives, so preview images are resolved from `StadiumGBD/render/thumbnail/stadium/<stadium name>.*`.

## Assignment And Settings Editors

The app can create and update `settings.ini` entries from the UI:

- stadium assignments by home team, round, or full tournament
- multi-stadium assignments for randomized stadium rotation
- scoreboard and TV logo assignments by tournament, round, or home team
- movie assignments by tournament, round, derby, or home team
- excluded competitions or rounds
- stadium net values and scoreboard display names
- chants entries under `FSW/Chants`

Changes saved through the editor are applied back into the runtime immediately where possible.

## Camera Packages

The Camera tab supports the exact package folder named:

```text
Anth's FIFA 16 AIO Camera Mod Package
```

The folder must contain `Instructions.txt`. Each camera preset is discovered from a child folder with a `data/` directory, and any `.png` files in that preset folder are used as preview images.

When a camera is applied, the preset's `data/` contents are synced into the FIFA `data/` folder. If `REGENERATOR.exe` is found next to the selected FIFA install, the app attempts to launch it after copying the files.

## Building The EXE

You can build the standalone executable with the included batch file:

```powershell
.\build_exe.bat
```

The batch file compiles the C++ overlay helpers when Visual Studio C++ tools are available. If they
are not installed, it uses the existing helper binaries in `bin/` and still runs the PyInstaller
package step.

The overlay's D3D compiler is explicitly bundled from `bin/D3DCOMPILER_47.dll`,
including builds that reuse the native helpers.

Or run PyInstaller directly:

```powershell
pyinstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller Server16Python.spec
```

The resulting executable will be created at:

```text
dist/Server16Python.exe
```

## How To Contribute

Contributions are welcome.

You can help by:

- fixing runtime bugs
- improving the overlay UX
- refining stadium, scoreboard, and movie workflows
- improving audio/chants behavior
- expanding documentation
- testing on different FIFA 16 setups

Suggested contribution flow:

1. Fork the repository.
2. Create a feature branch.
3. Make focused changes.
4. Test locally.
5. Open a pull request with a clear description.

## Notes For Contributors

- Keep Windows compatibility in mind.
- Avoid committing build outputs and local runtime artifacts.
- Prefer small, reviewable pull requests.
- If you change behavior tied to FIFA memory offsets or file routing, document it in the PR.

## Release Assets

Suggested GitHub release contents:

- `Server16Python.exe`
- `RELEASE_NOTES_v0.2.1.md`
- release notes summarizing major fixes and improvements
- optional screenshots or changelog excerpts

## Credits

- Original concept and workflow: CGFS 16 Server 16 for FIFA 16
- Python port and ongoing maintenance: this community project and its contributors

## Disclaimer

This project is an unofficial community tool for FIFA 16 modding workflows. Use it at your own risk and always keep backups of important game and mod files.

## Revisão local das implementações solicitadas

Lista baseada nos pedidos escritos desta conversa e no código local; não é uma
afirmação de que todas as funcionalidades do fork foram importadas. Os sete áudios
originais não foram retranscritos nesta revisão.

- Torcida: apoio/reclamação conforme placar, pausas/silêncio, fadiga e participação
  do visitante durante pausas e reação a gols estão no runtime local. A música de
  gol do visitante continua dependendo do módulo `AwayClubSong`.
- Volume geral somente da torcida: popup `Select + Start`, ajuste por direcional
  ou analógico, sem alterar música de gol ou entrada. A revisão evita que o fade
  sobrescreva o volume geral e que backups `.original.mp3` sejam sorteados.
- Correção Chant: remoção validada de ID3v2, backup preservado e substituição
  atômica. Arquivos com cabeçalho inválido não são reescritos.
- Abertura do painel pela barra de espaço permanece no fluxo existente.
- Indicador de atualização, aviso de local de instalação, configuração ImgBB,
  limpeza de cache e telas de início/fechamento estão no código local. A revisão
  encaminha atualizações visuais dos workers para a thread principal do Tk.
- Seletor de estádio: `F12` ou `Start` no pré-jogo, país/região, pesquisa sem
  acentos com aproximação e prioridade para correspondência exata, contador,
  setas, prévia e clube/escudo quando identificados sem ambiguidade. Teclado
  virtual controlável pelo controle, Aplicar e Cancelar; `Start` fecha sem aplicar.
- O seletor usa bloqueio de mensagens e polling de teclado/controle, inspirado
  no FIFA Mods Dev. Se o servidor deixar de enviar heartbeat, o bloqueio expira.
  Atalhos só ficam disponíveis quando os gates e o renderizador estão prontos.
  Proxies DXGI com vtable privada podem não ser interceptados.
- Aplicação manual usa o carregador existente, não grava atribuições em
  `settings.ini`, valida `model.rx3` antes de alterar assets e descarta conclusão
  de uma partida já expirada. Não foi adicionada lógica de modo carreira.
- Rollback DDS dos estádios: as prévias voltam à descoberta original em
  `StadiumGBD/render/thumbnail/stadium` com JPG/JPEG; DDS não é aceito nessa
  visualização. Os formatos originais adicionais do projeto foram preservados.
  O tratamento preexistente de escudos DDS não foi removido.
- O pedido de duas casas decimais em porcentagens foi cancelado e não aplicado.

Validação: 84 testes Python (no Python 3.10 usado pela build), teste
nativo com teclado/controle simulados e teste de renderização D3D11 por software
com restauração de estado e imagem ausente. Build recompilada e bibliotecas
embutidas conferidas. A integração com o FIFA real e diferentes controles ainda
precisa de teste; não foi executado nem instalado o novo servidor dentro do jogo.

Correção RAR após a falha registrada em 03/10/2026 às 07:39:23: a build anterior
passou a incluir `rarfile`, cujo caminho de extração individual com o `tar` do
Windows falhou no pacote real `BRA - Maracana - Flamengo.rar`. A extração agora
usa o arquivo RAR inteiro, prioriza UnRAR instalado (inclusive fora do PATH),
depois 7-Zip e tar, e valida tamanho/CRC dos membros em uma pasta temporária antes
de disponibilizá-los para aplicação. Não instala dependências durante o jogo.
Falha, arquivo incompleto, CRC inválido e timeout não publicam os arquivos
parciais. As texturas/crowd/glare opcionais ausentes preservam o baseline FSW,
como no carregador do fork, em vez de apagar a cópia nativa recém-restaurada.
Corrigido também o `IndexError` da entrada de times em menus sem HID disponível.

Revisão dos atalhos F12/Start: a DLL do seletor (`cgfs16_overlay.dll`) e o helper
x64 já são embutidos no EXE; não dependem de instalar uma DLL na pasta do FIFA.
A conexão com o canal tenta novamente se o Python ainda não estava pronto;
a inicialização também repete tentativas de injeção que falharam. O teste de
foco reconhece a janela principal quando o renderizador usa uma janela filha.
O catálogo carrega em background e descarta resultados após Cancelar, sem
interromper o heartbeat ou atualizar Tk fora da thread principal. Os logs do
servidor e `%TEMP%/cgfs16_overlay.log` registram prontidão e rejeição de atalhos.
Teste nativo isolado verifica conexão tardia, prontidão dos gates, reinício do
canal, janelas principal/filha e timers. Os testes usam canais/logs separados
do jogo. Esses testes não confirmam a abertura dentro do FIFA real; ao trocar
a build, feche o servidor e o FIFA antes do reteste para não manter a DLL antiga
em memória.

O card de estádios agora segue o layout claro solicitado: foto ampliada com
setas circulares, busca discreta, filtro de país, contador, nome do estádio e
escudo do clube quando identificado. Não exibe estado nem capacidade, nem
inventa esses dados. Cancelar fica à esquerda e Aplicar, em azul, à direita.
O teclado virtual usa teclas de ação mais largas e navegação correspondente
ao desenho. Ele é desenhado como painel independente na parte inferior do
jogo; o card fica no topo e as áreas de clique seguem as duas escalas. O
bloqueio de entrada e o carregador de estádios que já funcionavam permanecem.
Contadores exibem posição (`5 de 15`), quantidade filtrada e total instalado.
Prévias carregam em background, com cache limitado, loader e descarte de
respostas de uma seleção antiga. A transição de foto usa fade de 220 ms no
renderizador, sem atrasar nomes, botões ou contadores. O aviso de carregamento
D3D e o fallback Tk também usam fundo branco, texto escuro e barra azul.
Tiles de país usam bandeiras locais da [Flagpedia](https://flagpedia.net/download/api),
embutidas na build, sem rede durante o jogo. Prefixos conhecidos e aliases
do catálogo são mapeados; códigos desconhecidos continuam como texto sem
inventar bandeiras. O seletor continua aceitando prévias JPG/JPEG, sem DDS.

Correções de 03/10/2026 após os crashes das 11:51 e 11:53: os três cards de
carregamento podiam produzir 820 vértices em um buffer de 512. O renderer agora
reserva 1024 vértices na CPU/GPU e rejeita inserções além do limite; o teste D3D11
isolado cobre todas as combinações dos três cards, incluindo progresso completo.
O crash registrado pelo Windows era `0xc0000409` na DLL do overlay.

A limpeza de assets não substitui mais `pausemenuflow.nav`, o vídeo OUTRO nem
o bumper. Ela estava restaurando a navegação sem as ações de vídeo/TV, mesmo
com Movies habilitado. A inicialização, o lançamento, o bootstrap e a ordem
de aplicação são novamente idênticos à branch original; foram removidos o
pré-carregamento do vídeo no lançamento e sua reaplicação após o estádio.
As barras apenas observam as cópias existentes, e falhas de notificação não
interrompem a aplicação. Testes com arquivos temporários verificam prioridades,
fallbacks, pacotes parciais e preservação da navegação na limpeza. Esta validação
não substitui um teste de partida no FIFA real.

O foco do seletor e do painel de áudio usa um contorno azul de quatro pixels
lógicos, separado do conteúdo por branco. Aplicar selecionado fica azul-escuro,
com marcador externo e legenda de confirmação; não se confunde com o azul de
um botão sem foco. Movimento do mouse apenas seleciona, sem aplicar/editar;
um cursor parado não rouba o foco do controle. Não há nova renderização ao
passar por pontos diferentes do mesmo alvo. Teclado virtual e filtros de país
seguem o mesmo destaque. A extração/aplicação do estádio não foi modificada
por este ajuste de interface.

Extração RAR otimizada: o worker publica a pasta já extraída e validada por
renomeação somente sobre seu destino temporário vazio, com identidade
conferida e no mesmo volume. Bloqueios ou incompatibilidades usam
automaticamente a cópia validada anterior, sem extrair novamente. Tamanho,
CRC, caminhos e rejeição de links continuam obrigatórios; dados inválidos
nunca são aplicados. ZIP, pacote original e sequência de aplicação não mudam.
O log informa `Stadium extraction publication: rename` ou `copy` e o motivo.

Rotinas isoladas de desempenho: `scripts/benchmark_stadium.py` registra a
rodada inicial; `scripts/benchmark_rar_publication.py` compara a implementação
final sem conversão de arquivos. No Maracanã, três pares intercalados mediram
9,17 s antes e 6,88 s depois na mediana da extração completa (cerca de 25%).
Um bloqueio de renomeação simulado com o pacote real também passou pelo
fallback, com saída idêntica por SHA256. O cache de extração não foi implementado.
Tempos variam com disco/cache e não medem uma partida no FIFA. Resultados e
limitações estão em [docs/STADIUM_BENCHMARK_2026-10-03.md](docs/STADIUM_BENCHMARK_2026-10-03.md).

Volumes por confronto: durante a partida, abra o painel por `F12` ou
`Select + Start`. `Aplicar geral` grava o padrão dos dois sliders no
`runtime/settings.json` do servidor. `Aplicar específico` grava o par
mandante/visitante em `<FIFA>/FSW/audio_profiles.json`; a aplicação cria esse
arquivo quando uma instalação do FIFA é selecionada, se ele estiver ausente.
Arquivos existentes são validados e seus outros confrontos/campos preservados.

O perfil do confronto tem prioridade sobre o geral e é recuperado assim que
os IDs são lidos, inclusive após reiniciar, sem precisar abrir o painel.
`1043:545` e `545:1043` são confrontos diferentes. Os dois botões aplicam
o volume imediatamente ao áudio ativo. Aplicar geral também vale para a
partida atual, mesmo se houver um perfil específico salvo; esse perfil não
é apagado e volta a ter prioridade na próxima partida ou ao reiniciar.
Reabrir o painel na mesma partida mostra os volumes que estão em uso.
Cancelar não grava ajustes. Edições manuais do JSON são reconhecidas durante
o contexto da partida e ao reabrir o painel.

O arquivo tem `version: 1` e um objeto `matches`, cujas chaves são
`mandante:visitante`; cada entrada contém `chants` e `goal_hymns` em frações
de volume (`0.75` significa 75%). O painel normalmente vai de 0 a 100%; se
um volume de torcida antigo estiver acima de 100%, esse slider permite até
200% para exibi-lo e preservá-lo. Sliders não alterados preservam a precisão
original. JSON inválido, versão incompatível ou valores fora dos limites
usam o geral e não são sobrescritos; falhas de salvamento não aplicam o novo
volume. Atualizações usam arquivo temporário e substituição atômica.

### Revisão de áudio e atalhos (2026-10-03)

Os hinos de gol dos dois times tocam até o fim do `ClubSong.mp3`, sem corte
no reinício da jogada. O menu de pausa suspende o áudio; ao voltar, ele
continua da mesma posição e com o volume aplicado mais recentemente.
Uma pausa longa não consome o tempo restante do hino.
O gol visitante não inicia outra reação por cima da volta ao jogo depois
de um `ClubSong` executado. As configurações `AwayClubSong` e `AwayChants`
continuam sendo respeitadas. O áudio encerra nas páginas de resultado/fim
de partida ou ao abandonar para seleção de times, treino ou inicialização;
o menu de pausa `FluxHub` não é tratado como fim da partida.

Atalhos: `F12` ou `Start` abre o menu de público/estádio no pré-jogo; durante a
partida, `F12` ou `Select/Back + Start` abre o painel de áudio. Apertar o mesmo
atalho novamente fecha sem salvar. O painel de áudio permanece disponível
na pausa e em transições de página vazia de uma partida já reconhecida.
O controle deve estar disponível como XInput (Xbox ou controle compatível/
adaptado). A DLL aceita encadear o desvio XInput conhecido do FIFA Mods Dev,
mantendo o anterior; código desconhecido não é alterado.

Trocas manuais de estádio são específicas da partida, não da carreira inteira.
Ao voltar da visualização/pré-jogo para o KickOffHub, a escolha manual é mantida
se a partida ainda não começou. Depois de entrar na partida, o próximo
KickOffHub reinicia esse contexto e volta à seleção automática do mandante.
A cópia usa o ID de injeção inativo (176 ou 261), prepara modelo e texturas
fora dos arquivos ativos e só muda o ID após concluir a publicação. Falhas na
preparação/publicação ou na confirmação do ID restauram a cópia anterior;
se o Windows impedir essa restauração, o log informa a pasta de recuperação.
A mesma atribuição automática não é sorteada novamente a cada consulta.

Exemplo editável de perfil (mandante 1043, visitante 545):

```json
{
  "version": 1,
  "matches": {
    "1043:545": {"chants": 0.75, "goal_hymns": 0.50}
  }
}
```

### Clássicos, menu pré-partida e público (2026-10-04)

Cânticos extras ficam em `FSW/Chants/<pasta do chantsid>/Support/Rivals/<ID do adversário>/*.mp3`.
Os MP3 diretamente em `Support` continuam normais. Quando um cântico de apoio
já pode tocar, há 25% de chance de escolher o repertório desse adversário;
os especiais não ficam mais frequentes só porque há mais arquivos na pasta.
Para o visitante, usa-se o ID do mandante, somente com `AwayChants` habilitado.
Sem pasta/arquivos válidos, o comportamento anterior é mantido. Não há cópia
de áudio nem outro player: volumes, pausas, fades, gols e fim da partida usam
o motor existente. `Complaint`, `ClubSong.mp3` e `Entrance.mp3` não mudam.
Backups `.original.mp3` são ignorados; erro de abertura/reprodução de um
especial retorna ao repertório normal e exclui esse arquivo até a próxima partida.

No pré-jogo, `F12`/`Start` abre dois cards: público e estádio. Setas e `Enter`,
mouse ou direcional/analógico e `A` navegam. `Esc`/`B` volta; repetir o atalho
fecha o menu. Os atalhos diretos de teclado são:

| Tela | F1 | F2 | F3 / Esc |
| --- | --- | --- | --- |
| Menu inicial | Público | Estádio | Fechar |
| Público | Aplicar | Voltar | Voltar |
| Estádio | Aplicar (ou confirmar busca no teclado virtual) | Voltar | Voltar |
| Áudio da partida | Aplicar geral | Aplicar específico | Cancelar |

O controle de público lê o valor vivo do FIFA; o slider vai de 0 a 100,
mantendo a escala do atributo do plugin (o padrão nativo é 90). Abrir,
movimentar o slider e cancelar não altera o jogo. Aplicar exige confirmação
da ponte nativa, volta ao menu e vale apenas para a partida atual. O pedido
continua durante carregamento/partida; termina ao sair ou trocar o confronto,
fechar o Server ou perder sua comunicação. Não há perfil persistente de público.

A ponte está embutida em `cgfs16_overlay.dll`, incluída no EXE. Não substitui
`crowd_plugin.dll`, não edita `crowd.ini`, seus pesos, VLT ou arquivos CRWD.
O mod de carreira continua calculando/publicando o valor automático. Durante
um override confirmado, a ponte fornece o valor manual somente à entrada
estática da DLL de torcida; ao liberar, devolve a regra automática. No amistoso
usa o mesmo registro validado, sem criar uma carreira fictícia.

A integração é restrita ao build de `crowd_plugin.dll` fornecido no FIFA Mods Dev
(SHA256 `9f5f76a7bb48e185ad6e3158b4793f3a80d44cd857e052a7a96baee1ec248284`).
O bridge confere a identidade PE/código de referência, região privada gravável,
offset determinístico `0x364D0`, chave do registro e faixa do valor em cada escrita.
Nunca busca um float solto na memória. DLL ausente/desconhecida, alvo ambíguo
ou indisponível impede a aplicação, preservando o fluxo anterior. São aceitos
no máximo dois registros, como no plugin original. Logs da ponte ficam em
`%TEMP%/cgfs16_overlay.log`; status 0=DLL não suportada, 1=aguardando registro,
2=pronto, 3=confirmado, 4=falha. Testes isolados não substituem validação de
amistoso e carreira dentro do FIFA real.
