# Estádio de fundo do perfil e da carreira — Server16 0.2.14

Atualização 22/10/2026: preparação/extração fora da thread de desenho e fora
da trava compartilhada com ela. Resultados de uma seleção vencida não são
publicados. A DLL mantém o nome `frontend_stadium_native_v11.dll` por
compatibilidade com o retorno do ambiente do clube.

Capacidade e público vêm exclusivamente do pacote escolhido: `metadata.ini`
ou `stadium.ini` com `[stadium] capacity=... attendance=...`, seções
`[stadiumcapacity]`/`[stadiumattendance]` do FSW (nome do pacote como chave),
ou `ModCarrerMode/config/stadium_metadata.ini` (seção com o nome do pacote,
prioridade maior). Ausentes ficam vazios. Valores são pessoas, não porcentagens.
Estádios nativos preservam seus próprios dados. APT preserva Initialize,
ShowPriorityString, nome, escudo, input e saída nativos.

A DLL não envia teclas, mouse ou controle.
Os diagnósticos externos usam OpenProcess 0x410, somente leitura.

A recarga reproduz o seletor nativo do perfil: canal fe, evento
FE::FIFA::FreeRoamChangeFeStadium, ID 0x3b971407 e payload de um byte.
A emissão corresponde a 4c4672c..4c4678c. A fila nativa 4a15f30 copia o payload
sob sua própria trava. O worker prepara o pacote; o FIFA executa a transição
na sua própria sequência de eventos.

Preparação (43630eb -> 435e8c0) e carregamento (436311b -> 4361970) recebem
cópias com os mesmos campos FE +e8/+ec. Todos os outros campos são preservados.
As duas etapas de GameFlow::Render são acompanhadas: quadro FE de abertura
(3a1a168 -> 4361d70) e cenário 3D (3a19f7f -> 44d8ce0). A v4 acompanhava
apenas a primeira e deixava de consumir pedidos após entrar no cenário 3D.
O observador usa o thread do jogo nas duas etapas; a extração acontece no
worker antes de enfileirar a recarga. Pedidos só são emitidos nas páginas de
menu, perfil e panorâmica. Boot/legal não podem emitir o evento de mudança
do perfil, pois o jogador/rig ainda está sendo inicializado.

Modelo, texturas e distribuição de cadeiras usam o mesmo pacote. O carregador
5cbd1b7 -> 5cbb330 identifica exclusivamente a torcida FE:
[3504748] -> +10 -> +90 -> ponteiro da implementação. A abertura em
5cbb3cb -> 5cbe930 usa crowd_day.dat do cache. A partida mantém seu caminho.
O callback Lua da torcida recarrega a rota do slot independentemente da ordem
do callback do estádio e usa NoSeats.rx3 quando fornecido. Sem posicionamento
customizado, oculta cadeiras genéricas para evitar sobrepor as do estádio nativo.
O bypass de visibilidade da v3 foi retirado; o despacho original é preservado.

No automático, início usa favorito e carreira usa o clube ativo do serviço de
carreira, sem exigir data/estatísticas da API de torcida. Escolhas manuais ficam
por clube em [frontend_stadium_clubs]. A preferência global v3 é migrada para
o clube do último carregamento. RAR/ZIP permanecem intactos; o cache preserva
todos os recursos auxiliares.

O painel mostra Estádio de fundo. Aplicar agora solicita recarga imediata;
Voltar também aplica uma escolha alterada. Esc cancela sem aplicar.
Na carreira, a opção fica no painel F12. runtime/frontend_stadium_live.ini
(UTF-16) informa PID, clube, solicitação, fase e erro. Fases: 1 preparando,
2 aguardando a transição, 3 carregada, -1 erro. A fase 3 confirma o estado do
carregador, não a qualidade visual do cenário.

Imagem sobreposta é ocultada somente para rotas 3D disponíveis. Panorâmica
customizada usa nome do pacote e escudo do clube; capacidade/ano são ocultados.
Os estados mainMenuWithStadium (início) e MainMenuHub (carreira) usam o
componente FIFA com BOOTFLOW como imagem de fallback. O componente BOOTFLOW
fixo do FIFA Friends não recebe a decisão do BackgroundDP. O componente FIFA
recebe o parâmetro transparente da DLL para uma rota 3D válida. Sem rota,
mantém a imagem BOOTFLOW. Os wrappers APT anteriores foram preservados.

Validação: regressões Python e C++; scripts completos stadium.lua/crowd.lua
em Lua 5.1; wrappers APT em VM limitada; helper congelado executado contra
o RAR real do ABC em pasta temporária, verificando cache e SHA-256 do original.
Na sessão 38560, 20 carregamentos concluíram sem erro, incluindo a entrada
automática Flamengo/Maracanã na carreira. A troca foi confirmada pelo usuário.
Na sessão 46676, o menu inicial exibiu o estádio 3D sem a arte FIFA Friends.
A carreira usa a mesma alteração de componente. A conferência visual da
carreira e do clube sem rota 3D permanece para validação do usuário.

Instalação: tools/install_frontend_stadium.py, com FIFA e Server16 fechados.
Backup inclui Lua, EXE, configuração, enabled.txt e UI. O manifesto contém hashes.
O lançador abre o FIFA com cwd igual à pasta do executável, independentemente
da pasta de onde o Server16 foi iniciado.
DLL ativa: frontend_stadium/frontend_stadium_native_v5.dll. Eventos do log:
PREPARE_ASYNC, NATIVE_PROFILE_RELOAD_QUEUED, LOAD_SAME_ROUTE, CROWD_ROUTE,
MODELS_DISPATCHED, SCENE_MONITOR_ACTIVE, RELOAD_COMPLETE e erros explícitos.

Restauração: tools/disable_frontend_stadium.py restaura stadium.lua e crowd.lua,
desativa somente as versões deste mod e restaura a UI registrada. O EXE anterior
do Server16 fica no backup para restauração manual.
