# Server16 — FIFA Friends

Seu painel para preparar a partida e personalizar o FIFA 16.

Escolha o estádio, ajuste a apresentação, controle o áudio e configure recursos do [FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12) pelo Server16. O painel reúne as opções antes e durante o jogo, com navegação por mouse, teclado ou controle, conforme a tela.

**Atualizado em:** 19/10/2026 · **Plataforma:** Windows / FIFA 16 compatível

## Overlay da carreira — 19/10/2026

No hub da carreira, **Select + Start** ou **F12** abre um painel próprio com
**Transferir para outro clube** e **Finanças > Solicitar verba**. A carreira aberta
é reconhecida automaticamente. Revise o pedido e saia da carreira sem salvar novamente. Aguarde a confirmação
no menu principal e carregue o mesmo save. O Server guarda um backup antes de aplicar.
Clubes e divisões acompanham os dados do save; verba está disponível para treinador.
Veja o [guia da overlay da carreira](docs/OVERLAY_CARREIRA.md) para uso, limites e validação.

O público automático também dá mais peso à Libertadores e às competições
brasileiras, usando a próxima partida real do clube. Veja os valores e ajustes
no [guia de público por competição](docs/PUBLICO_COMPETICOES.md).

## Aberturas — 18/10/2026

- **Base Robson 12.12:** cada modelo usa a pasta com o ID atual da competição ou fase. A fase com pacote próprio tem prioridade; sem esse pacote, herda o da competição principal. Os módulos traduzem identidades de carreiras antigas para o CompData instalado.

Os ícones da carreira usam uma imagem por ID do INI. A DLL prepara os BIGs e os
nomes nativos de DDS do calendário e dos cards, com cabeçalhos DXT5 corrigidos.
O teste do usuário após reiniciar confirmou os ícones no jogo. Entradas e suportes
3D ainda aguardam confirmação visual em partida.

Use a atualização correspondente do [FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12):
ela inclui `dinput8.dll`, os três módulos corrigidos e a biblioteca de ícones.
Mantenha os BIGs do calendário e reinicie FIFA/Server após copiar os arquivos.
Nesta base, a Série A usa `1761.png` e a Libertadores `1460.png` em
`data/ui/imgAssets/careerCompetitionIcons/`; consulte `COMPETICOES.txt` para os demais IDs.

## Menu durante a partida — 18/10/2026

Abra com **Select + Start** no controle ou **F12**. O painel agora reúne **Música**
(cânticos da torcida e hinos de gol), **Gráficos** (física de roupas) e **Câmera**.
Em Câmera, ajuste **Câmera do jogador**, **Modo** e **Campo de visão**. Ligar/desligar fica
salvo e é recuperado nas próximas sessões, sem precisar abrir o menu. A suavização
é sempre **Forte** e o enquadramento sempre **Campo e bola**, com olhar neutro.
O modo pode ser **Primeira pessoa** ou **Terceira pessoa · carreira**. Este último
mantém a câmera atrás do jogador selecionado, mostra o corpo inteiro e suaviza
as viradas e a translação sem copiar os balanços da cabeça. Limita a aceleração das
viradas e suaviza trocas para jogadores próximos. Na terceira pessoa, **Distância** oferece
**Perto**, **Intermediária** e **Afastada**, com transição suave. As escolhas ficam salvas.
A abertura padrão é **85° nos dois modos**, sem ampliação automática com a posse.
Cada modo guarda seu próprio ajuste: 75°–150° na primeira pessoa e 60°–90° na terceira,
em passos de 5°. A terceira pessoa usa uma posição mais recuada para preservar as proporções.
Com posse, o olhar mantém mais espaço
para o campo, dá atenção ao controle próximo da bola e volta a levantar após
um passe ou finalização. O novo enquadramento é experimental;
a sensação em domínios e chutes precisa ser avaliada jogando.

O controle da câmera pertence ao Server; não precisa abrir o painel externo.
Fechar apenas o overlay mantém a câmera escolhida. **F10** devolve a câmera original;
fechar o Server também desativa o efeito naquele momento, preservando a escolha
salva para a próxima abertura. **F10** salva a opção desligada. Use a câmera nativa
**Profissional** nos dois modos, pois o efeito depende desse comportamento nativo. A saída do
centro fixa a posição na cabeça sem o atraso do filtro. Uma pequena folga à frente da cabeça
reduz a chance de o cabelo aparecer nas viradas.

## Novidades — 17/10/2026

- **Compatibilidade com a base v12.11/Honduras:** ícones acompanham a identidade do calendário instalado; aberturas usam diretamente as pastas dos IDs atuais.

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
2. Coloque no arquivo o **nome completo ou ID da competição**. Nesta edição, por exemplo: **`1761.png`** ou **`BRA - Brasileirao Serie A.png`**.
3. Abra o Server atualizado, aguarde alguns segundos e inicie o FIFA.

Pronto: o Server prepara o calendário e os cards da Central/Competições a partir da mesma imagem, com o mesmo ID do INI. **Não é preciso editar tabelas, preparar DDS ou extrair BIG.** A lista **`COMPETICOES.txt`**, gerada na mesma pasta, mostra os nomes aceitos na sua instalação.

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
