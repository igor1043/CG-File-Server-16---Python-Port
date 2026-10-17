# Server16 — FIFA Friends

Seu painel para preparar a partida e personalizar o FIFA 16.

Escolha o estádio, ajuste a apresentação, controle o áudio e configure recursos do [FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12) pelo Server16. O painel reúne as opções antes e durante o jogo, com navegação por mouse, teclado ou controle, conforme a tela.

**Atualizado em:** 17/10/2026 · **Plataforma:** Windows / FIFA 16 compatível

## Novidades — 17/10/2026

- **Ícones automáticos da carreira:** copie uma imagem com o nome ou ID da competição. O Server identifica, converte e cadastra sozinho, sem editar tabelas.
- **Movimento das camisas e calções:** ative ou desative a física de roupas pelo painel. Sua escolha fica salva para as próximas aberturas.
- **Controle durante a partida:** o painel de F12 permite alterar a física e confirma a resposta do jogo quando o módulo compatível está carregado.
- **Encerramento revisado:** o Server conclui suas operações e libera os próprios recursos ao sair.

## O que você pode personalizar

- **Estádio:** busca, prévia e escolha do estádio para o confronto.
- **Apresentação da partida:** mascotes, objetos de abertura, fogos, fumaça e confete, com os módulos do V12.
- **Física de roupas:** movimento das camisas e calções; começa desligado e preserva a escolha feita por você. Recurso experimental do V12.
- **Torcida:** ajuste de ocupação e volume, com confirmação dos módulos compatíveis.
- **Cânticos e hinos:** áudios dos clubes, rivalidades e perfis de volume.
- **Narração:** escolha entre os perfis e bancos de áudio instalados.
- **Música de abertura:** perfil de áudio para a apresentação.
- **Placar, TV e vídeos:** pacotes associados às competições e partidas.
- **Ícones das competições:** importação de PNG, JPG, WEBP ou BMP para a carreira.

As telas Próxima Partida, Meu Time e Competição, o banco com 12 reservas, as sete substituições, a cabine do VAR e os objetos 3D pertencem ao V12. O Server trabalha junto dos módulos e dos pacotes de recursos instalados.

## Comece em poucos passos

1. Abra **Server16Python.exe** e selecione sua instalação do FIFA, se solicitado.
2. Deixe o Server aberto e inicie o jogo pelo botão de iniciar o FIFA.
3. No pré-jogo, abra o painel com **F12** ou **Start**, conforme o contexto.
4. Escolha suas opções e confirme em **Aplicar**. **Voltar/Cancelar** descarta as alterações ainda não aplicadas.

Para ativar o movimento das roupas, entre em **Configurações da partida > Física de roupas > Aplicar**. Durante a partida, use **F12 > Ajustes da partida**. Camisa e calção são controlados juntos.

## Adicione um ícone sem planilha

1. Com o FIFA fechado, copie um **PNG ou JPG** para `data/ui/imgAssets/careerCompetitionIcons/`, dentro da pasta do jogo.
2. Coloque no arquivo o **nome completo ou ID da competição**. Nesta edição, por exemplo: **`1738.png`** ou **`BRA - Brasileirao Serie A.png`**.
3. Abra o Server atualizado, aguarde alguns segundos e inicie o FIFA.

Pronto: o Server ajusta o tamanho, converte a imagem e cadastra o ícone. **Não é preciso abrir o settings.ini, editar o index.tsv ou preparar um DDS.** A lista **`COMPETICOES.txt`**, gerada na mesma pasta, mostra os nomes aceitos na sua instalação.

Prefira PNG com fundo transparente. Para atualizar um logo, substitua a imagem original; deixe apenas uma imagem por competição. Os originais e os backups ficam preservados. Se você colocar a imagem com o FIFA aberto, o Server processa quando o jogo estiver fechado. O botão de iniciar o FIFA conclui a importação antes de abrir o jogo.

Nomes desconhecidos, duplicados ou ambíguos e imagens inválidas são explicados na aba **Logs**. A identificação usa o nome do arquivo; não reconhece o campeonato pelo desenho do logo. O recurso adiciona imagens às competições já instaladas, sem criar campeonatos.

## Atalhos úteis

| Ação | Atalho |
|---|---|
| Aplicar nos painéis de configurações, público e narração | **F3** |
| Voltar ou cancelar nesses painéis | **F4** |
| Alternar a física de roupas, com o módulo compatível | **F6** |
| Painel durante a partida | **F12**, conforme o contexto |

Os comandos disponíveis também aparecem nos próprios painéis. Depois de atualizar o executável ou os módulos, reinicie o Server e o FIFA uma vez.

## O que acompanha a experiência

Use o Server com o **FIFA Friends V12 e seus módulos compatíveis**. Estádios, modelos, imagens, narrações, músicas e vídeos dependem dos pacotes instalados separadamente. A cabine do VAR é um recurso visual do V12; a física de roupas é experimental.

## Mais informações

- [Roteiro de uso](docs/ROTEIRO_FIFA_FRIENDS.md).
- [Guia técnico: arquivos, execução pelos fontes e testes](docs/GUIA_TECNICO.md).
- [Todas as melhorias do FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12).
