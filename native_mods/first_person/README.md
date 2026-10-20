# Primeira pessoa no Server16

Componente x64 `server16_first_person_v11.dll`, carregado pelo Server usando o helper
existente `cgfs16_inject.exe`. O controle é o mapa `Local\FIFA16_FirstPersonCamera_v4`,
80 bytes, versão 4, declarado em `camera_channel.h` e `first_person_runtime.CameraShared`.
O Server publica owner/heartbeat e comando; a DLL publica ack/estado/erro. Não há
processo de painel externo. Sem heartbeat por três segundos ou ao fechar o Server,
a câmera desativa. F10 também desativa. O Server salva ativação e abertura e
recupera a escolha na inicialização, sem exigir abertura do menu. Reiniciar o Server reaproveita a DLL já
carregada, inclusive se o diretório temporário do PyInstaller mudou.

A revisão v6 adia a ativação até o próprio FIFA inicializar o cache de nomes dos
ossos (flag RVA 3518200 no executável 577DE45C). Apenas carregar BCEngine não basta:
consultar o osso antes disso aciona a inicialização preguiçosa contra uma tabela
ainda ausente e derruba o jogo. O erro transitório 3 indica espera, mantém a escolha
salva e tenta de novo automaticamente, sem chamar o resolvedor durante a espera.

O protótipo usa o BCEngine desta compilação do FIFA (timestamp 577DE45C), com dois
desvios de vtable verificados antes da escrita. Captura Head pela matriz animada,
com a fonte no sexto argumento do coletor, e substitui a saída do comportamento
ThirdPerson após a função original. Valida jogador, GameData, idade, matriz e estado
2 (KickOff), 14 (OutOfPlay, incluindo espera para reinício) ou 15 (Play). A rotina
nativa atualiza o jogador selecionado antes de ler a fase; excluir 14 interrompia
o acompanhamento antes de a bola entrar em jogo. O modo de jogo usa FOV
85 graus por padrão, mantendo a lente constante com ou sem a bola para conciliar
a visão do campo com a bola nos pés. Dá mais atenção ao controle próximo nativo
(`isInPaceControl`, comportamento +A10), sem tratá-lo como identificador universal
de drible. Ao soltar a bola, prioriza o campo por 650 ms; isso inclui passes e chutes,
sem distinguir a animação. Não gira o heading em direção à bola. O Server mantém
enquadramento Campo e bola (1) e viés neutro (0). O menu expõe ativação, modo,
FOV por modo, suavização da cabeça na primeira pessoa e distância na terceira pessoa.
A primeira pessoa aceita 75–150° e a terceira 60–90°, sem aumento automático com posse. A posse usa
PossesorPlayerId (+A30) comparado ao jogador seguido (+9CC). A folga de segurança
mantém o olho pelo menos 21 cm à frente do centro animado da cabeça quando a
ocultação da cabeça não está disponível. A revisão v11 restaura essa posição, sem recuo.

Modo 1 (Terceira pessoa · carreira) usa `career_camera.h`: câmera 480 cm atrás da
raiz e 230 cm acima, com referência de mira 850 cm à frente / 110 cm de altura.
Órbita horizontal com resposta de 400 ms, limite de 1,5 rad/s e aceleração de
4 rad/s². A translação da raiz passa por dois filtros (100 e 140 ms), sem copiar
altura/pitch/roll animados da cabeça. A bola à frente atrai parcialmente a direção;
o corpo inteiro cabe no FOV padrão 85°. Sem teste de colisão contra o cenário.
Não usa `headClearance`, que empurraria a câmera para dentro da posição de primeira
pessoa. Alternar o modo reinicia os filtros. O campo reservado de CameraStatus
reflete o modo para diagnóstico, preservando o tamanho público de 56 bytes.

`head_camera_stabilizer.h` filtra o movimento relativo ao corpo, com quatro intensidades,
e reinicia ao trocar jogador/contexto, em intervalos grandes ou teletransporte. O
corpo continua acompanhando a translação sem atraso. Inclinação lateral é atenuada.
Suavização da cabeça: 0 Média (mesma resposta da antiga configuração fixa Forte),
1 Alta, 2 Extra alta e 3 Agressiva. Aumentar o nível filtra progressivamente mais
as rotações e oscilações locais, sem atrasar a translação da raiz do corpo.
`head_smoothing` é salvo nas preferências; arquivos anteriores começam em Média,
preservando ativação, modo, distância e FOV. A terceira pessoa usa seus próprios filtros.
Durante KickOff e OutOfPlay, a posição local acompanha a cabeça imediatamente; a suavização
dos ângulos continua. A mudança de fase e saltos locais maiores que 45 cm também
reiniciam o filtro para recuperar a pose inicial sem aproximação lenta.
O export `CameraTrackingStatus` (80 bytes) permite conferir raiz, olho da cabeça,
olho da câmera, idade da captura, fase, modo, validade e contadores.

Fontes derivadas do experimento local em
`J:\mods\fifa 16\estudos fifa 16\97_PRIMEIRA_PESSOA_RAM_20261018`.
Compilar: `scripts\build_first_person.cmd`; testar matemática:
`scripts\test_first_person.cmd`. `build_exe.bat` inclui a DLL no executável do Server.
O painel antigo deve ser fechado e seu protótipo parado ou o FIFA reiniciado antes
de ativar esta versão, pois ambos usam as mesmas funções da câmera.

Distância (campo int32 final do canal): 0 Perto (480/230 cm), 1 Intermediária
(750/320 cm), 2 Afastada (1150/450 cm), com filtros de 160 e 180 ms para a transição. Preferências versão 4
guardam o FOV de cada modo separadamente; ambos começam em 85°. A primeira pessoa
sincroniza a pose aplicada com o cache nativo +BE0, usado na interpolação de transições.

A revisão v11 retira integralmente o hook Player::GetLod e as cópias de
malhas introduzidos nas revisões v8–v10. O dump de 19/10/2026 20:27:15
registrou uma leitura nula em FIFA+4ADC62E no render, com retorno para a
DLL v10+2CDD e o caminho BatchPlayer em FIFA+43BE32B.
Foi restaurado o gerador da revisão v7, mantendo somente o controle dos quatro
níveis de suavização. A câmera volta à folga anterior, à frente da cabeça;
cabeça, olhos, boca e cabelo permanecem com o render original, inclusive ao
alternar o jogador. Não há hook de render nem descritores substituídos.
`head_mesh_filter.h` e seu teste ficam apenas como experimento isolado, sem
inclusão no componente instalado. A ocultação de malhas não é entregue nesta revisão.

Na terceira pessoa, trocas de jogador de até 25 m preservam o filtro em vez de
reiniciá-lo. Trocas mais distantes, pausa longa, novo contexto ou mudança de fase
readquirem a câmera para evitar travessias longas do estádio. Os filtros de translação descritos são exclusivos da terceira pessoa.

## Validação pendente

O teste em jogo de 19/10/2026 confirmou atraso na saída de bola e na retomada após gol, mesmo com o reset matemático da âncora. Portanto, esta revisão não resolve essas duas transições. O acompanhamento durante lances normais foi relatado como correto.

A pasta `experimental/` preserva o teste v12 de cabeça oculta/recuo e os observadores de transição em RAM. Esses fontes não são incluídos no EXE nem carregados automaticamente. `head_mesh_filter.h` preserva o wrapper nativo completo de 232 bytes e a revisão do descritor, mas continua fora do runtime v11. A integração da ocultação e a correção do atraso dependem de validação adicional em jogo.
