# Server16 — FIFA Friends

Painel para preparar a partida e personalizar o FIFA 16, integrado ao [FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12).

**Versão: 0.2.30** · Windows / FIFA 16 compatível

## Revisão atual

- Listas nativas de **placar**, **vídeo pré-jogo** e **ocupação do estádio**, com leitura dos catálogos INI ao preparar as opções. Novos itens instalados são incorporados à lista.
- Seletor de estádio nas opções do jogo com pesquisa, país e imagem de prévia, preservando a escolha ao voltar.
- Abertura dos painéis com **F12** ou **Select + Start**, com tratamento da liberação dos botões para evitar ações duplicadas no FIFA.
- Fundo da carreira selecionável entre imagem estática, estádio 3D e vestiário V3. A sala preparada é reutilizada pelo ambiente da carreira.
- **Esvaziar cache e logs** com execução em segundo plano e proteção dos recursos em uso. A limpeza preserva saves, históricos financeiros e do mercado de técnicos, preferências e assets originais. Logs têm limites por arquivo e por conjunto; somente dois resumos compactos de diagnóstico de sessões anteriores são mantidos.
- Preparação dos auxiliares e diagnóstico da inicialização alinhados à versão instalada no jogo. Os fontes publicados foram comparados aos módulos embutidos no executável validado.

O FIFA Friends V12 acompanha as telas de finanças, incorporação financeira até 500 milhões, painéis da central, títulos por temporada, mercado de técnicos e ambientes 3D. Os históricos pertencem a cada carreira. Modelos, artes, minifaces, músicas e demais assets externos são distribuídos separadamente dos fontes; dados pessoais de saves e caches não são publicados.


## O que você pode personalizar

- **Estádio:** busca, prévia e escolha do estádio para o confronto.
- **Apresentação da partida:** mascotes, objetos de abertura, fogos, fumaça e confete, com os módulos do V12.
- **Física de roupas:** movimento das camisas e calções; começa desligado e preserva a escolha feita por você. Recurso experimental do V12.
- **Torcida:** ajuste de ocupação e volume, com confirmação dos módulos compatíveis.
- **Cânticos e hinos:** áudios dos clubes, rivalidades e perfis de volume.
- **Música de abertura:** perfil de áudio para a apresentação.
- **Placar, TV e vídeos:** pacotes associados às competições e partidas.
- **Ícones das competições:** importação de PNG, JPG, WEBP ou BMP para a carreira.

As telas Próxima Partida, Meu Time e Competição, o banco com 12 reservas, as sete substituições, a cabine do VAR e os objetos 3D pertencem ao V12. O Server trabalha junto dos módulos e dos pacotes de recursos instalados.

## Comece em poucos passos

1. Abra **Server16Python.exe** e selecione sua instalação do FIFA, se solicitado.
2. Deixe o Server aberto e inicie o jogo pelo botão de iniciar o FIFA.
3. No pré-jogo, abra o painel com **F12** ou **Select + Start**, conforme o contexto.
4. Escolha suas opções e confirme em **Aplicar**. **Voltar/Cancelar** descarta as alterações ainda não aplicadas.

Para ativar o movimento das roupas, entre em **Configurações da partida > Física de roupas > Aplicar**. Durante a partida, use **F12 > Ajustes da partida**. Camisa e calção são controlados juntos.

## Adicione um ícone sem planilha

1. Com o FIFA fechado, copie um **PNG ou JPG** para `data/ui/imgAssets/careerCompetitionIcons/`, dentro da pasta do jogo.
2. Coloque no arquivo o **nome completo ou ID da competição**. Nesta edição, por exemplo: **`1761.png`** ou **`BRA - Brasileirao Serie A.png`**.
3. Abra o Server atualizado, aguarde alguns segundos e inicie o FIFA.

Pronto: o Server prepara o calendário e os cards da Central/Competições a partir da mesma imagem, com o mesmo ID do INI. **Não é preciso editar tabelas, preparar DDS ou extrair BIG.** A lista **`COMPETICOES.txt`**, gerada na mesma pasta, mostra os nomes aceitos na sua instalação.

Prefira PNG com fundo transparente. Para atualizar um logo, substitua a imagem original; deixe apenas uma imagem por competição. Os originais e os backups ficam preservados. Se você colocar a imagem com o FIFA aberto, o Server processa quando o jogo estiver fechado. O botão de iniciar o FIFA conclui a importação antes de abrir o jogo.

Nomes desconhecidos, duplicados ou ambíguos e imagens inválidas são explicados na aba **Logs**. A identificação usa o nome do arquivo; não reconhece o campeonato pelo desenho do logo. O recurso adiciona imagens às competições já instaladas, sem criar campeonatos.

## Atalhos úteis

| Ação | Atalho |
|---|---|
| Aplicar nos painéis de configurações e público | **F3** |
| Voltar ou cancelar nesses painéis | **F4** |
| Alternar a física de roupas, com o módulo compatível | **F6** |
| Painel durante a partida | **F12**, conforme o contexto |

Os comandos disponíveis também aparecem nos próprios painéis. Depois de atualizar o executável ou os módulos, reinicie o Server e o FIFA uma vez.

## O que acompanha a experiência

Use o Server com o **FIFA Friends V12 e seus módulos compatíveis**. Estádios, modelos, imagens, narrações, músicas e vídeos dependem dos pacotes instalados separadamente. A cabine do VAR é um recurso visual do V12; a física de roupas é experimental.

## Mais informações

- [Todas as melhorias do FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12).
