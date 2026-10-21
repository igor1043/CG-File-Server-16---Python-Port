# Panoramicas cinematograficas de drone

Acrescenta 39 trajetos a panoramica FE dos menus do FIFA 16, build
`577DE45C`. Nao altera os arquivos DAT/BIG nem os pacotes MUSE originais.
O motor continua executando e selecionando suas tomadas. O diretor libera
o enquadramento original por 8 segundos na entrada e 24 segundos entre os
extras. A duracao base e 52 segundos; as chegadas aereas duram de 73 a 83 segundos. A revisao v2 remove a interpolacao
de posicao entre tomadas: escurece, troca a camera com a tela preta e revela
a proxima tomada. Cada troca usa 1,5s para escurecer, uma breve pausa preta
e 1,5s para revelar. O movimento do trajeto fica parado durante essas fases,
sem atravessar o estadio para alcancar a proxima camera. A ordem percorre
todos os trajetos habilitados antes de repetir.

As cenas sao: voo baixo, decolagem central, travessia diagonal, orbita do
centro, aproximacao do gol, revelacao do campo junto ao gol, passeio lateral,
arco do escanteio, vista vertical, descida cinematografica, vista elevada da
arquibancada (filmada de dentro do campo) e afastamento panoramico.

A v3 acrescenta entradas pelo alto da lateral, pelo gol, pelo canto e pela
lateral oposta; revelacao aerea do estadio; saida do campo para fora do
estadio; grua central; travelling junto a linha de gol; arco amplo sobre o
campo; retrato do circulo central; tomada junto ao travessao; e paralaxe da
arquibancada. As novas tomadas usam curvas cubicas e variacao gradual de
lente, com aceleracao e desaceleracao suaves. A primeira extra e uma das
novas entradas aereas, depois dos 8 segundos originais.

A v4 acrescenta doze tomadas: travessia da boca dos dois gols; aproximacao
da marca do penalti ate cada gol; percurso completo da linha central nos
dois sentidos; orbita de 360 graus com raio de 7m dentro do circulo central;
giro completo de camera a partir do centro; travelling junto aos dois
travessoes; arco frontal do gol; e grua baixa junto a uma trave. A primeira
extra passa a ser a nova travessia da boca do gol. As duas rotacoes completam
uma volta inteira, com inicio e final suaves. A selecao usa 64 bits para
visitar tambem as tomadas acima da posicao 31 sem truncar a lista.

A v5 acrescenta uma orbita externa de 360 graus: elipse com semieixos de
110m e 95m, camera a 108m e alvo no centro do campo. O trajeto contorna o
estadio inteiro e fecha na mesma pose. Na revisao 6 das tomadas, a duracao
padrao passa de 83,2 para 98,8 segundos, limitada a 95–180 segundos. A
velocidade durante a rotacao diminui cerca de 17%, preservando os 8,32 segundos
de aceleracao e desaceleracao nas pontas, no padrao. Os cortes e o trajeto
permanecem iguais. Perfis com limite de altura abaixo de 100m excluem essa orbita.

A revisao 6 acrescenta duas cenas. `stadium_horizontal_profile_orbit` completa
uma elipse de 165m por 145m de semieixos, a 65m de altura, olhando para um
ponto a 20m no centro do estadio. Esse alvo enquadra o perfil da estrutura,
com inclinacao de aproximadamente 15–17 graus para baixo, incluindo o horizonte.
A volta dura 130 segundos no padrao, limitada a 120–220 segundos. Perfis com
altura maxima abaixo de 65m excluem essa cena. `halfway_line_full_traverse`
percorre os 68m completos da linha de meio-campo, de uma lateral a outra,
a 2,4m de altura e olhando para a frente. O ritmo e constante no trecho
central, com rampas curtas nas pontas; a duracao padrao e 70,2 segundos.
A sequencia comeca pela orbita alta, a nova orbita horizontal e a travessia,
seguindo pelas outras tomadas sem repetir antes de completar o ciclo habilitado.

As coordenadas sao relativas ao campo, em centimetros. As 18 tomadas
internas anteriores ficam dentro de X +/-45m, Z +/-26m. As novas tomadas
perto das linhas chegam a X +/-50m e Z +/-33,5m, dentro de um campo padrao
105 x 68m. As cameras param antes do plano das redes; as marcas de penalti
ficam a X +/-41,5m e os gols a +/-52,5m. As seis aereas anteriores chegam a 118m
no eixo longitudinal e 108m no lateral, com altura maxima padrao de 110m.
Somente a nova orbita de perfil amplia o raio para 165m/145m; o novo
percurso central chega exatamente a Z +/-34m nas laterais.
Elas passam por cima da borda das arquibancadas antes de descer para o
campo. Perfis com altura maxima abaixo de 80m excluem as aereas em vez de
achatar a camera contra a cobertura. Os trajetos foram testados abaixo de
5m/s na duracao padrao, exceto as duas orbitas externas, abaixo de 10m/s.
As lentes permanecem entre 48 e 68 graus.

Isso nao e deteccao de colisao: modelos com coberturas excepcionais ou
campo fora do padrao precisam de validacao/perfil. A visualizacao do lado
de fora depende de o pacote do estadio possuir essa geometria. As chegadas
sao aereas, olhando para o interior do estadio, sem atravessar fachadas.
Nenhuma malha, textura, horario ou iluminacao e alterada/carregada pelo mod.

Instale `panorama_drone/panorama_drone_v5.dll` em `ModCarrerMode/mods` e
habilite essa unica versao em `enabled.txt`, depois de `frontend_stadium`
quando esse mod estiver presente. API nativa ModHost v1; nao requer uma
alteracao no EXE do Server16. Inicia com o jogo e funciona sem overlay.

Configuracao: `ModCarrerMode/config/panorama_drone.ini`, relida a cada 500ms.

- `enabled=0`: volta as panoramicas originais.
- `duration_seconds`: 20 a 120, padrao 52; chegadas aereas multiplicam esse tempo por 1,4 ou 1,6, limitadas a 180 segundos. A orbita alta multiplica por 1,9 (95–180 segundos), a de perfil por 2,5 (120–220 segundos) e a travessia completa por 1,35.
- `original_interval_seconds`: 10 a 180, padrao 24.
- `initial_original_seconds`: 0 a 120, padrao 8.
- `transition_seconds`: 1 a 8, padrao 3; metade para escurecer, metade para revelar, mais pausa preta de aproximadamente 180ms.
- `height_limit_cm`: 1000 a 14000, padrao 11000.
- `route_scale_percent`: 60 a 100, padrao 100.
- `[shots]`: cada trajeto pode ser desabilitado individualmente.

Se o frontend_stadium estiver instalado, o nome real do estadio da rota
determina um identificador FNV-1a UTF-16, exibido no status. Uma secao
`[stadium_XXXXXXXX]` com esse identificador hexadecimal pode sobrescrever
`height_limit_cm` e `route_scale_percent` apenas para aquele estadio. Os
slots compartilhados 176/261 nao sao tratados como identidade do estadio.

Integracao: encadeia a chamada GameFlow::Render em `3A19F7F`, verificando
opcode, build e destino. Aceita a funcao nativa `44D8CE0` ou o relay do
frontend_stadium; aguarda seu hook se a DLL estiver carregada. Preserva
o callback anterior e suas recargas. Depois dele entrega a pose ao estado
de camera efetivamente consumido pelo render, caminho validado no teste
de RAM. Nao instala hooks de GetFrame nem de animacao/atores.

A v2 usa o alpha de desvanecimento nativo da apresentacao em scene+225C,
recebido do frame+740 (produtor BCEngine 5D420, consumidor FIFA 3A27F64).
Acrescenta apenas o escurecimento necessario, preservando um fade nativo
mais forte. O valor e emprestado e restaurado pelo mesmo criterio de
igualdade dos campos de camera. Valores fora do intervalo 0..255 tornam
o enquadramento inelegivel. Trocas de pose so ocorrem depois de um frame
com opacity=1 e ainda retornam opacity=1 no frame da troca, inclusive
em baixa taxa de quadros. A confirmacao visual desse efeito no jogo e
separada dos testes da sequencia e exige o FIFA aberto.

Apenas fase FE 1 e cameras `BC: Stadium FE <numero>` sao elegiveis.
Kit select, FE Step, introducao, partida, replays e cenas do tecnico/mascote
nao sao elegiveis. Os campos emprestados sao restaurados antes da proxima
chamada e no Stop somente quando ainda contem os bytes escritos pelo mod.
Nao restaura flags ou campos novos do motor. O modulo fica fixado para
proteger callbacks ainda em transito; o Stop retira apenas seu proprio hook.

Diagnostico: `runtime/panorama_drone_status.ini` e export
`PanoramaDroneStatus` v5, com PID, readiness, active, shot, progresso,
pose, camera original e fadeOpacity. O INI informa fade_opacity e
transition=black_fade. Log: `ModCarrerMode/logs/panorama_drone.log`.
`ready=1` comprova instalacao do hook; `applied` comprova entrega da pose,
mas a aprovacao visual e a compatibilidade de cada estadio sao verificacoes
separadas.

Build: `scripts/build_panorama_drone.cmd`, MSVC x64. Os testes cobrem os
39 trajetos, limites, velocidade, matriz, perfis, intervalos originais,
transicoes, cortes totalmente pretos nos dois sentidos com FPS alto/baixo,
rotacao completa, desativacao e saida da panoramica.

Atualizacao v3: o instalador migra uma unica vez os antigos valores padrao
32s/32m para 52s/110m e acrescenta os novos interruptores de tomadas.
Valores personalizados, tomadas desabilitadas e perfis por estadio sao
preservados. A DLL e versionada para permitir a instalacao com FIFA aberto.
O status v3 acrescenta shot_count, duration_seconds e exterior.
Na v4, a migracao acrescenta os doze novos interruptores e atualiza apenas
scene_pack_revision. Duracoes, cenas desabilitadas e perfis existentes sao
preservados. As novas cenas entram habilitadas. Reabra o FIFA uma vez para
carregar a nova DLL; o EXE do Server16 nao precisa ser recompilado.

A revisao 6 conserva o nome da DLL v5 e sua API, atualizando apenas as
tomadas e sua ordem. O instalador acrescenta os dois interruptores novos e
atualiza `scene_pack_revision=6`, preservando as escolhas ja salvas.
