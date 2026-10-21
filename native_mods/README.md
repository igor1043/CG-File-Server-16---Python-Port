# Módulos nativos do Server16

Este repositório mantém os fontes nativos, scripts de compilação e testes.
As DLLs compiladas do jogo são distribuídas na [branch FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12),
com uma pasta por módulo e uma DLL atual por pasta. O [índice do pacote](https://github.com/igor1043/fifa-mods/blob/fifa-friends-v12/ModCarrerMode/mods/README.md)
informa os destinos e as configurações.

| Diretório | Componente / destino |
|---|---|
| `frontend_stadium/` | Estádio de fundo: `ModCarrerMode/mods/frontend_stadium/frontend_stadium_native_v11.dll`; preparador em `ModCarrerMode/tools/` |
| `panorama_drone/` | 39 tomadas: `ModCarrerMode/mods/panorama_drone/panorama_drone_v5.dll` |
| `mascot/` | Mascotes: `ModCarrerMode/mods/mascot_single/mascot_goal_line.dll` |
| `pyro/` | Pirotecnia e bloqueio durante os pênaltis: `ModCarrerMode/mods/stadium_pyrotechnics/stadium_pyrotechnics.dll` |
| `first_person/` | Câmeras do jogador; biblioteca embutida no Server16 |
| `career_native/`, `career_jobs_runtime/` | Integração nativa da carreira |
| `career_overlay/`, `career_ui_assets/` | Layouts e recursos da carreira |
| `extra_scenes/` | Cenas de técnicos/mascotes: fontes preservados, módulo desativado na distribuição |
| `narration/` | Biblioteca preservada; seletor, aplicação automática e avisos ocultos no Server16 0.2.8 |

Os scripts em `scripts/` compilam em diretórios de build. Para estádio de fundo
e panorâmica, `FRONTEND_STADIUM_OUTPUT` e `PANORAMA_DRONE_OUTPUT` permitem escolher
uma pasta temporária. Os instaladores em `tools/` publicam os resultados com
backup. Caches, diagnósticos e modelos locais permanecem fora do Git.

`server16_py/__init__.py` concentra as opções internas
`EXTRA_SCENES_AVAILABLE=False` e `NARRATION_PICKER_AVAILABLE=False`.
Os testes habilitam explicitamente os componentes preservados quando necessário.

## Configurações da apresentação da partida

O Server escreve apenas `ModCarrerMode/config/match_presentation.ini` dentro da
pasta do FIFA selecionada no Server. Ausência do arquivo usa estes padrões:

```ini
[match]
mascots=1
pyrotechnics=0
entrance=0
goal=0
schema=1
```

Aplicar salva os quatro valores juntos, por substituição atômica. Voltar não
salva. O arquivo só é criado ao aplicar. Opções salvas são recuperadas ao abrir
o painel; não se alteram as regras de público nem o volume dos áudios.

As DLLs compatíveis consultam esse arquivo a cada 250 ms. Só a DLL de mascotes
decide a aparência/animação; só a DLL de pirotecnia decide o disparo dos efeitos.
Desligar o mestre bloqueia abertura e gol sem apagar as escolhas dos subitens.
A pirotecnia continua respeitando o próprio `pyro.ini`: `enabled=0` continua
desabilitando o módulo. A regra de gol segue a do mod existente (gol mandante).
Modelos e assets precisam continuar instalados; estas DLLs não os incluem.

Os diretórios `mascot` e `pyro` são snapshots dos fontes locais do FIFA Friends
V12, com ajustes mínimos de permissão. Preservam a seleção de atores, animações,
replay, cores, verificação das assinaturas e limpeza na thread do jogo.
Não substituem o carregador nem alteram estádio, vídeo, placar ou executável.
Não instalar por cima de uma revisão diferente: integrar os pequenos ajustes ao
fonte novo antes de recompilar. O instalador confere os hashes de origem.

## Instalador histórico MatchPresentation

O pacote histórico `dist/MatchPresentation` inclui o EXE, duas DLLs e um
instalador para aquele snapshot. Para a distribuição atual, use o instalador
do FIFA Friends V12. A ferramenta histórica confere hashes específicos e não
substitui uma atualização completa. Seu comando original é:

```powershell
& 'CAMINHO_DO_PACOTE\Install-MatchPresentation.ps1' -GameRoot 'PASTA_DO_FIFA' -IncludeServer
```

O instalador verifica todos os arquivos antes de copiar e faz backup das duas
DLLs e do EXE. Recusa outra revisão de DLL, para preservar atualizações de
outros chats. Não cria entrada no carregador nem instala assets ausentes.
Para voltar, feche o jogo e copie os arquivos do backup aos mesmos destinos.
Não copia o INI: ele só nasce quando você aplica no painel. Os padrões da DLL
já são mascotes ligados e pirotecnia desligada, mesmo sem esse arquivo.

## Controle e teclado

O Server procura primeiro o `fifa16.exe` ao lado do próprio EXE e usa o
`FSW/settings.ini` dessa instalação, mesmo que haja um caminho antigo salvo.
Sem FIFA local, mantém a instalação externa válida já selecionada. Se a
configuração estiver ausente, exibe um aviso traduzido e não inicia a aplicação
de assets nem cria um INI vazio para substituir o original. As traduções vêm
dos recursos embutidos no EXE; não é preciso copiar a pasta de idiomas.

Controle compatível com XInput: direcional/analógico seleciona ou ajusta, A
confirma, B volta. No áudio, X aplica geral e Y aplica para o confronto.
Ícones são monocromáticos. Os cards do menu e o botão Fechar não têm ícones.
Desconexão troca as dicas de volta para teclado sem perder uma edição aberta.

Teclado: F12 abre/fecha. No pré-jogo, F3 público, F4 estádio e F5 configurações;
Esc fecha. Nos painéis público/configurações, F3 aplica e F4 volta. Durante a
partida, as categorias usam F3 Música, F4 Gráficos, F5 Câmera e F8 Fechar.
Os comandos de áudio aparecem no painel correspondente. Setas e Enter continuam disponíveis.

## Retorno da panorâmica e testes de fluxo

Os testes `test_asset_runtime_flow.py`, `test_frontend_stadium.py` e
`test_penalty_shootout.py` cobrem o contexto da partida, os caminhos do estádio
de fundo e a permanência do placar na disputa de pênaltis. Não reaproveite
assets apenas pelo ID do clube: sessão, adversário, competição e estado do
carregamento também participam do fluxo.
