# Configurações da apresentação da partida

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

## Instalação e recuperação

O pacote `dist/MatchPresentation` inclui o EXE, as duas DLLs e o instalador.
Não foi aplicado ao jogo nesta revisão. Apenas copiar o EXE **não** habilita os
switches nas DLLs antigas. Com o FIFA e o Server fechados, execute no PowerShell:

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

Teclado: F12 abre/fecha. No menu, F1 público, F2 estádio, F3 configurações,
F4 fecha. Nos painéis público/configurações: F1 aplica e F2 volta. No áudio:
F1 geral, F2 confronto, F3 cancela. Setas e Enter continuam disponíveis.

## Estudo: retorno da panorâmica

Hoje, em `server16_py/app.py`, retornar a `KickOffHub` reinicia a geração de aplicação,
exceto quando já há seleção manual/público manual preservável. Por isso um
estádio automático pode provocar nova aplicação do estádio, placar e vídeo.

É viável reaproveitar a aplicação enquanto for a **mesma partida** e os assets
não tiverem sido restaurados/substituídos. A chave deve considerar sessão,
times, competição/rodada, seleção e estado dos assets, não apenas ID mandante.
Um retorno ao menu, final da partida ou mudança de adversário deve invalidar
essa chave; trocar manualmente o estádio deve continuar aplicando normalmente.
Uma simples cache só pelo time reutilizaria assets incorretos na próxima
partida da carreira. Nenhuma mudança nesse fluxo foi feita nesta revisão:
este ponto é apenas o estudo solicitado, sem confirmação de runtime no FIFA.
