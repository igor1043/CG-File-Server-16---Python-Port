# FIFA Friends — roteiro simples da nova versão

Este documento explica, de forma simples, o que foi colocado nesta versão do
Server 16 Python Port e como usar as funções principais.

## 1. Para começar

1. Abra o `Server16Python.exe`.
2. Na primeira execução, selecione o arquivo `FIFA 16.exe` quando o programa pedir.
3. Confirme se a pasta escolhida é a instalação que será usada pelo jogo.
4. Deixe o Server 16 aberto antes de iniciar o FIFA 16.
5. Se o jogo já estiver aberto, feche o FIFA e o Server e abra os dois novamente
   quando trocar o EXE ou uma DLL.

O programa cria e usa a pasta `runtime` para configurações locais. Os arquivos
do jogo continuam dentro da pasta do FIFA, principalmente em `FSW` e nas pastas
`StadiumGBD`, `ScoreBoardGBD`, `TVLogoGBD` e `MoviesGBD`.

## 2. O que foi melhorado

### Torcida e cânticos

- A torcida reage ao placar e diferencia mandante e visitante.
- Cânticos de apoio, reclamação, pausa e reação a gol continuam usando o
  mecanismo original do Server.
- A torcida visitante pode participar quando o módulo `AwayChants` estiver ativo.
- O `ClubSong.mp3` do mandante e do visitante toca até o final do áudio.
- Se o jogo for pausado, o hino pausa na posição atual. Ao voltar, continua do
  mesmo ponto.
- Quando a partida termina ou sai para uma tela de encerramento, o áudio é
  finalizado corretamente.
- Arquivos MP3 com uma tag ID3v2 que causa problema no Windows podem ser
  corrigidos automaticamente. O arquivo original é preservado como backup.

### Cânticos especiais de clássicos

Para criar cânticos contra um adversário, use esta estrutura:

```text
FIFA 16/
  FSW/
    Chants/
      pasta-do-chantsid/
        Support/
          Rivals/
            ID_DO_ADVERSARIO/
              canto-1.mp3
              canto-2.mp3
```

Os cânticos normais continuam diretamente em `Support`. A pasta `Rivals` é
opcional. Quando ela existir e a partida corresponder ao ID do adversário,
existe uma chance controlada de tocar um canto especial. Se faltar a pasta ou
o arquivo não puder ser reproduzido, o Server volta automaticamente ao áudio
normal.

### Volume dos áudios

Durante a partida, abra o painel com `F12` no teclado ou com `Select/Back +
Start` no controle.

Há dois controles:

- `Cânticos da torcida`: volume geral dos cânticos.
- `Hinos de gol`: volume geral dos hinos de gol.

Use as setas, o direcional, o analógico, o mouse ou o teclado virtual da tela.

Os botões são:

- `Aplicar geral` — aplica imediatamente e grava o padrão geral.
- `Aplicar específico` — aplica imediatamente e grava somente para o confronto
  atual, na ordem mandante x visitante.
- `Cancelar` — fecha sem aplicar a alteração feita na tela.

O botão geral não apaga um perfil específico já existente. Ele vale para a
partida atual, mas o perfil específico volta a ter prioridade em uma nova
partida ou depois de reiniciar o programa.

Os perfis específicos ficam em:

```text
FIFA 16/FSW/audio_profiles.json
```

O arquivo é criado automaticamente. Um exemplo é:

```json
{
  "version": 1,
  "matches": {
    "1043:545": {
      "chants": 0.75,
      "goal_hymns": 0.50
    }
  }
}
```

Nesse exemplo, o cântico fica em 75% e o hino em 50% para o mandante 1043
contra o visitante 545. Inverter os times cria outro confronto.

### Entrada pré-jogo

Se o módulo `TeamEntrance` estiver ativo e existir `Entrance.mp3` na pasta do
chants do time, o áudio de entrada pode ser executado antes da partida.

### Menu antes da partida

No pré-jogo, pressione `F12` ou `Start`. O menu mostra dois cartões:

- `Controle de público` — altera a ocupação da torcida para a partida atual.
- `Escolha seu estádio` — abre o seletor de estádio.

No painel de público, o valor é ajustado de 0% a 100%. `Aplicar` confirma a
alteração somente depois que o mod de torcida confirma a comunicação. Se a
confirmação falhar, a regra automática é mantida.

O controle de público é temporário: não grava uma carreira nova nem altera o
`crowd.ini`. Ele funciona por cima do valor automático enquanto a partida e a
comunicação estiverem válidas.

### Seletor de estádio

No cartão de estádio:

- a tela abre já posicionada no estádio selecionado anteriormente;
- o campo de busca encontra nomes mesmo com diferenças de acentos;
- `L1` e `R1` trocam o país/região quando o controle oferece esses botões;
- as setas, o mouse, o teclado e o controle mudam o estádio;
- a tela mostra a posição, por exemplo `5 de 15`;
- a imagem tem carregamento em segundo plano, loader e transição suave;
- `Aplicar` aplica apenas para a partida atual;
- `Cancelar` fecha sem aplicar;
- abrir o atalho novamente fecha a tela sem aplicar o rascunho.

As imagens de prévia são procuradas na pasta original:

```text
FIFA 16/StadiumGBD/render/thumbnail/stadium/
```

Nesta versão, a prévia de estádio usa JPG/JPEG, conforme o fluxo original.
Não é necessário converter a pasta de imagens do jogo para DDS.

### Arquivos de estádio e segurança

O Server prepara o estádio fora dos arquivos ativos e só publica a troca depois
de validar a operação. Se a aplicação falhar, a cópia anterior pode ser usada
como fallback. A troca manual fica limitada à partida atual; ao começar outro
confronto, a seleção automática do mandante volta a ser considerada.

Arquivos ZIP continuam funcionando. Arquivos RAR/RAR5 podem usar UnRAR, 7-Zip
ou `tar`, conforme o que estiver disponível no Windows. A extração é validada
antes da aplicação para evitar publicar uma pasta incompleta.

### Placar, TV e vídeo

Os módulos de `TvLogo`, `ScoreBoard` e `Movies` continuam seguindo o fluxo do
Server original. A interface apenas mostra o andamento em caixas e barras de
progresso; ela não troca a ordem de aplicação dos assets.

Quando `Movies` está ativo, o Server usa os arquivos configurados em:

```text
FIFA 16/FSW/Nav/
```

É importante manter os arquivos de vídeo e navegação originais disponíveis
para que o fallback possa ser restaurado.

### Controle pelo teclado e controle

- `F12`: abre o menu de estádio/público no pré-jogo ou o painel de áudio na partida.
- `Start`: faz a mesma função do `F12` quando o overlay está pronto.
- `Select/Back + Start`: abre o painel de áudio durante a partida.
- `Esc` ou `B`: volta/cancela na tela atual.
- `F1`, `F2` e `F3`: confirmam as ações principais quando a tela indica esses botões.
- `Enter` ou `A`: confirma o item selecionado.
- `Espaço`: alterna o overlay geral do Server quando o FIFA está ativo.

O controle deve ser reconhecido como XInput, como um controle Xbox ou um
controle compatível. Se o atalho não responder, feche o FIFA e o Server, abra
o Server primeiro e depois inicie o jogo.

## 3. Funções da tela principal

Na tela do Server, os módulos mais importantes são:

- `Stadium`: estádios e seletor de estádio.
- `TvLogo`: logos de transmissão.
- `ScoreBoard`: placares.
- `Movies`: vídeos e vinhetas.
- `Chants`: torcida e cânticos.
- `AwayChants`: cânticos do visitante.
- `AwayClubSong`: hino do visitante após gol.
- `TeamEntrance`: áudio de entrada pré-jogo.
- `DiscordRPC`: presença do Discord, se desejado.

Também existem opções para manter o Server aberto quando o FIFA fechar,
mostrar a notificação de carregamento e selecionar estádio aleatório quando
essa opção estiver habilitada.

## 4. Banco de dados e DLLs

O projeto inclui uma ponte de 32 bits para ler o banco do FIFA usando
`FifaLibrary16.dll`. Ela fica embutida no build junto com o Python x86 usado
por esse worker. O usuário normalmente não precisa executar esse worker
manualmente.

O botão de regenerar BH executa a rotina quando o FIFA estiver fechado e os
arquivos necessários estiverem disponíveis.

## 5. Limpeza, atualização e solução de problemas

- `Verificar update` consulta se existe uma versão mais nova.
- O aviso de instalação ajuda a identificar quando o Server foi apontado para
  uma pasta diferente da instalação do FIFA.
- `Limpar cache` remove somente previews/importações geradas; não remove seus
  assets do FIFA nem o arquivo de configurações.
- Se o painel não abrir, confirme que o overlay e o FIFA estão usando a mesma
  sessão e reinicie ambos.
- Se um estádio não tiver imagem, confira o nome do arquivo JPG/JPEG e o
  prefixo do país na pasta de thumbnails.
- Se o áudio não tocar, confira se `Chants` está ativo, se `settings.ini`
  possui `chantsid` para o time e se o MP3 pode ser reproduzido pelo Windows.
- Se o vídeo ou o placar não aparecer, confira se os módulos correspondentes
  estão ativos e restaure os arquivos originais do FIFA antes de testar de novo.

## 6. Build para desenvolvimento

Para gerar o EXE a partir do código:

```powershell
build_exe.bat
```

O build inclui o overlay, o helper nativo, a ponte de banco e o Python x86
embutido quando esses arquivos estão presentes em `bin/`.

Antes de enviar uma alteração, rode os testes:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Os testes cobrem áudio, perfis por confronto, cânticos de rival, seletor de
estádio, aplicação segura, RAR, ponte de público e ciclos de vida da partida.

## 7. Resumo para o usuário final

1. Abra o Server e selecione o FIFA 16.
2. Ative os módulos que pretende usar.
3. Inicie o FIFA.
4. No pré-jogo, use `F12`/`Start` para escolher estádio e público.
5. Durante a partida, use `F12` ou `Select/Back + Start` para ajustar os volumes.
6. Use `Aplicar geral` para o padrão ou `Aplicar específico` para aquele confronto.
7. Feche o Server somente depois de sair do jogo, se quiser que ele restaure os
   assets nativos corretamente.
