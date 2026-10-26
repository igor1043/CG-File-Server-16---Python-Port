# Revisão local para teste — 26/10/2026

Status: revisão liberada para commit, push e pacote pelo usuário em 26/10/2026.
As notas abaixo preservam a sequência dos testes locais; a entrega final é
descrita no README e no RELEASE_20261026.md do V12.

## Server16 0.2.19

O `cgfs16_inject.exe` apontado no alerta do Defender não acompanha mais o
executável congelado e não é chamado pelos clientes da interface, câmera ou
propostas. Esses módulos são carregados pelo host de plugins do próprio jogo,
com os arquivos declarados em `ModCarrerMode/mods/enabled.txt`. O Server conecta
os canais já carregados; não inicia o antigo carregador em outro processo.

Nenhuma configuração do Defender foi alterada. Arquivos em quarentena não
foram restaurados. Não há garantia de ausência de outros alertas: a classificação
no computador do Robson ainda precisa ser conferida com a revisão completa.
Para análise oficial de um possível falso positivo:
https://www.microsoft.com/en-us/wdsi/filesubmission

## Vestiário

- O APT envia `Server16RoomScene` ao dispatcher nativo já existente de eventos.
- A captura valida página, PID da sessão, clube, nonce e sequência antes de
  publicar uma pequena caixa de comandos. A câmera aplica o comando no frame
  proprietário, com intervalo de leitura de 100 ms.
- O worker não inicia mais a varredura de grandes áreas privadas da RAM.
- Quando a tela é preparada para o clube/sessão, publica a prontidão e a fila
  existente do proprietário da interface recarrega somente a view do vestiário.
  Isso permite atualizar os controles sem sair e voltar ou descarregar o 3D.
- Pacote inalterado não recarrega a cada entrada; PID, contexto, época, clube,
  data e hash da tela continuam validados pela fila nativa.

Testes offline cobrem captura e aplicação por seis entradas consecutivas,
comandos duplicados e de outra sessão/clube, ABI dos eventos originais, fila
da tela e restauração da câmera. A experiência real após reiniciar o FIFA
ainda depende do teste local. Assets estáticos não foram alterados; a cabine
de campo permanece e a sala interna do VAR continua fora da implementação.


### Nome do estádio na Próxima partida (revisão local)

A prévia deixou de depender apenas de `stadiums.name`, que identifica o modelo
compartilhado por vários clubes. Agora respeita a ordem do card nativo: seleção
da competição no FSW, seleção do mandante no FSW, nome personalizado do clube em
`stadiumassignments.stadiumcustomname` da carreira/DB e, por último, nome do modelo.
A tabela de nomes personalizados passou a ser incluída na leitura da carreira.
A capacidade mantém sua leitura anterior; não foi estimada a partir do nome.

Aplicado no código e no APT inicial das pastas de desenvolvimento e do jogo.
Testes: 29 testes da prévia (incluindo mudança de mandante e nomes personalizados)
e teste nativo de publicação dos títulos, todos aprovados. Conferido com a DB
instalada: Millonarios tem modelo `_Stadion Hanguk`, nome personalizado
`Estádio El Campín` e título FSW `Estadio Nemesio Camacho "El Campín"`.
A reprodução offline da última prévia mudou Volta Redonda de `_Stadio Classico`
para `Raulino de Oliveira`. Ainda não houve conferência visual desta revisão em
uma nova sessão do FIFA. Nenhum save, executável ou configuração de segurança foi
alterado. Revisão apenas local, sem commit, push ou novo ZIP de distribuição.
Evidências: `code-release/stadium_title_20261026/local-install.json`.


### Próxima partida: escalações em três colunas (revisão local)

Aplicado no APT nativo: campos maiores nas laterais, cabeçalhos da mesma largura
do campo, painel central com nome e logo da competição lida dos assets já
instalados no jogo, data, horário, estádio, localização quando resolvida pelo FSW,
confrontos registrados na carreira e últimos cinco resultados concluídos de cada
clube. O cabeçalho superior também identifica o local. Nomes longos da competição
e do estádio foram divididos em campos de texto independentes para evitar cortes.
O mapa das escalações continua recebendo a atualização nativa do StartingXIDP.

O confronto direto é limitado aos jogos concluídos presentes no snapshot da
carreira, em todas as competições, e é identificado como tal. Datas futuras,
partidas não jogadas e placares inválidos não entram. Quando faltam dados, a tela
mostra o estado vazio. Não foram inventados clima, temperatura, vento, colocação
ou pontos da tabela. Nenhum novo catálogo de imagens foi criado.

Mantidas as três páginas e as legendas originais BACK/LAS_LR, com teclado e
analógico esquerdo. O painel central é ocultado nas demais páginas. Passaram 33
testes da prévia, incluindo navegação, binds de dados, alinhamento do header,
limites dos jogadores, ausência de fixture, histórico e troca de mandante.
As três páginas do APT gerado foram renderizadas e inspecionadas offline; ainda
não houve conferência desta revisão numa nova sessão do FIFA. Não houve alteração
de EXE, DLL ou save nesta revisão. Sem commit, push ou ZIP de distribuição.
Evidências e imagens: `code-release/preview_layout_20261026/`.


### Vestiário: movimento do menu, quadro e luz (revisão local)

Abrir Cenas agora envia o comando idempotente de retomar (-3), preservando o
movimento em curso e limpando eventual pausa deixada pela interface anterior.
A legenda usa o HelpItem ADVANCE original do FIFA para Cenas, mantendo BACK para
Voltar. Selecionar uma cena continua levando àquela cena; navegar pelo menu não
interrompe a câmera. A revisão do APT passou a 64, com verificação compartilhada
no preparador e no sinal de prontidão para evitar voltar ao APT anterior.

O foco do quadro mudou de 348 para 300 unidades e de FOV 57 para 53. Os glifos
são desenhados com sobreamostragem 3x (antes 2x), fontes de competição/táticas
maiores e textura final RX3 4096x4096, com os mesmos 13 níveis de mipmap. O seed
room/runtime/indoor_ambient.txt define 0.90 no buffer de luz dos objetos do
vestiário, em lugar do padrão 0.65. O código de iluminação nativo e as luzes do
estádio não foram modificados. O recurso do quadro foi versionado como r63.

Foram aprovados 19 testes do vestiário e 33 da prévia. O diretor nativo de câmera
foi exercitado offline com os 910 obstáculos reais do ambiente: oito rotas até o
quadro, transição do enquadramento anterior e retomada durante movimento, sem
colisões. Aplicados código, seed e APT nas pastas de desenvolvimento/jogo; o
auxiliar específico do vestiário foi reiniciado e confirmou a revisão 64. O FIFA,
o Server16 e os auxiliares financeiros continuaram abertos. Não houve escrita no
save, troca de EXE/DLL, commit, push ou ZIP. Falta conferência visual desta revisão
em jogo. Evidências: code-release/room_visual_20261026/.

Esclarecimento dos 11 titulares: o auxiliar extrai a geometria/texturas e fixa a
pose; a engine do FIFA carrega o conjunto estático como GameplayProp RX3 no
estádio. Não é uma renderização WebGL sobreposta, mas também não instancia onze
atores com o pipeline completo de personagens da partida. Os materiais foram
simplificados e a projeção dinâmica das sombras no gramado ainda não está
integrada neste caminho. Esta revisão não implementa nem afirma corrigir essas
sombras.
