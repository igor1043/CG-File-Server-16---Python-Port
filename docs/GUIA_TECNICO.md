# Server16 Python — FIFA Friends

## Ajustes da partida e câmera em primeira pessoa

O atalho **Select + Start / F12**, durante a partida, abre Música, Gráficos e Câmera
no overlay existente. Música mantém os perfis geral e específico do confronto;
Gráficos controla a física de roupas. Câmera oferece somente ativação, modo e campo
de visão, em passos de 5. Modos: Primeira pessoa (0) e Terceira pessoa · carreira
(1), ambos na câmera nativa Profissional. Padrão de 85 graus nos dois, sem ampliar
automaticamente com posse. A primeira pessoa aceita 75–150 graus e a terceira 60–90.
Na terceira pessoa, Distância seleciona Perto, Intermediária ou Afastada.
Suavização Forte (perfil 2), enquadramento Campo e bola (1) e viés neutro (0)
são fixos. O submenu Personalizar e os outros seletores foram removidos.
No FIFA, selecione a câmera **Profissional** para usar a primeira pessoa.

`first_person_runtime.py` controla a DLL `bin/server16_first_person_v7.dll` por mapa
`Local\FIFA16_FirstPersonCamera_v4`, de 80 bytes, versão 4, com comandos confirmados
pelo jogo. Os últimos quatro int32 são FOV, inclinação em graus, modo e distância (0–2). A DLL valida a versão
e os slots nativos antes de intervir, mantém o acompanhamento na troca de jogador
e permite o acompanhamento na saída do centro (KickOff). O enquadramento combina
a posse, posição da bola e o indicador nativo de controle próximo. Depois de
soltar a bola, o olhar prioriza o campo por um curto intervalo; não distingue a
animação de chute de um passe. Uma pequena folga em frente à cabeça reduz a
chance de o cabelo aparecer nas viradas suavizadas.

`runtime/first_person_camera.json` versão 4 salva `enabled`, `mode`, `distance`,
`fov_first_person` e `fov_career`. A migração fixa o padrão solicitado de 85 nos
dois modos; novos ajustes ficam separados por modo e sobrevivem à troca. O runtime
é criado na inicialização do Server e restaura a ativação sem abrir o menu,
inclusive após trocar o processo do FIFA. Desconexão, fechamento ou falha do hook
não apagam a ativação salva. F10 volta à câmera original e salva desligado após
confirmar estado estável por 250 ms. Uma pausa do Server maior que 1,5 s reafirma
a escolha para não confundir o watchdog do heartbeat com F10. Sem heartbeat por
três segundos a DLL desativa o efeito. Fechar só o overlay mantém o efeito.
O Server reaberto reutiliza a DLL já carregada no mesmo FIFA.
O painel externo anterior deve estar fechado; se aquele protótipo ainda estiver
carregado e usando as funções, reinicie o FIFA uma vez para usar a integração.

`scripts/build_first_person.cmd` compila o módulo; `scripts/test_first_person.cmd`
valida a matemática e exercita o canal da DLL em um processo de teste, incluindo
rejeição de executável incompatível. Os testes Python cobrem categorias, volta de
submenus, volume sem regressão e persistência. O build normal inclui o módulo no
executável do Server. Recompile e reinicie o Server para atualizar o menu; se mudar
a DLL nativa já carregada, reinicie também o FIFA.

Terceira pessoa · carreira usa `career_camera.h`: posição Perto a 4,80 m atrás / 2,30 m
acima da raiz, Intermediária a 7,50 / 3,20 m e Afastada a 11,50 / 4,50 m. A mudança
de distância/altura usa dois filtros de 160 e 180 ms. Mira 8,50 m à frente e 1,10 m de altura.
A translação usa filtros de 100 e 140 ms; a órbita tem resposta de 400 ms, velocidade
limitada a 1,5 rad/s e aceleração a 4 rad/s². Mantém pitch de enquadramento e roll neutro, sem seguir os balanços da
cabeça. A bola à frente pode atrair levemente a direção da câmera; uma bola atrás
não provoca giro forçado. Trocar modo/fase reinicia os filtros; jogadores próximos
(até 25 m) preservam a transição, e saltos maiores readquirem a câmera. A proteção
contra cabelo se aplica somente à primeira pessoa, preservando a posição atrás
do corpo neste modo. Não há sondagem de colisão contra objetos do estádio.

Em KickOff (2) e OutOfPlay (14, incluindo espera para reinício), a posição relativa
à cabeça é imediata, preservando a suavização dos ângulos. O antigo bloqueio de
14 fazia a câmera voltar à saída nativa antes de a bola entrar em jogo. A seleção
do jogador continua atualizando nessas fases. Mudanças entre 2/14/15 e correções
de pose local maiores que 45 cm
reiniciam o filtro, evitando arrasto da âncora inicial.
A primeira pessoa também mantém o cache nativo de pose (+BE0, 0x64 bytes) coerente
com a pose aplicada, pois a interpolação nativa o usa nas transições de reinício.
Esse cache é copiado pelo gerador nativo em 8AB29..8ABC8 e lido em 8AAE7.

A aplicação de estádio automática conserva a geração ao voltar da prévia e,
assim como a manual, valida a fase antes de publicar arquivos e confirmar o ID.
Ao sair do pré-jogo, uma aplicação pendente é revertida sem trocar o ID; novas
aplicações ficam bloqueadas para evitar misturar a geometria com texturas em cache.

Painel para configurar partidas do FIFA 16, escolher estádios e administrar apresentação, cânticos e áudio. Trabalha com os módulos do [FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12).

## O que está disponível

| Recurso | Funcionamento |
|---|---|
| **Configurações da partida** | Liga ou desliga mascotes, pirotecnia, fogos na entrada, fogos nos gols e objetos de abertura da competição. Aplicar salva; Voltar cancela. |
| **Objetos de abertura** | Prepara o conjunto pelo ID da competição e da fase. Em amistosos, dois clubes da mesma liga usam a entrada dessa liga. O padrão é Sim; modelo ausente ou inválido deixa a partida sem o conjunto. |
| **Estádio** | Escolha para o confronto com busca, prévia e navegação por teclado, mouse ou controle. |
| **Placar e TV** | Usa os pacotes associados à competição e à fase. |
| **Ícones da carreira** | Coloque uma imagem com o nome ou ID da competição na pasta dos ícones. O Server converte e cadastra automaticamente, sem editar tabelas. |
| **Física de roupas** | Desativada por padrão; salva a escolha do usuário nas próximas aberturas. No pré-jogo, Configurações da partida > Física de roupas > Aplicar. Durante a partida, F12 > Ajustes da partida permite ligar/desligar imediatamente, com confirmação do jogo. Controla camisa e calção. |
| **Público** | Ajusta a ocupação quando o módulo nativo confirma a comunicação. |
| **Cânticos e hinos** | Usa os áudios dos clubes, perfis de volume e cânticos de rivalidade. |
| **Narração** | Escolhe os perfis externos disponíveis; os bancos de áudio são separados. |
| **Música de abertura** | Usa o perfil externo configurado para a apresentação. |
| **Câmeras e vídeos** | Aplica os pacotes configurados para a partida. |

As abas **Próxima Partida**, **Meu Time** e **Competição**, a cabine do VAR, mascotes, bolas extras e outros objetos 3D são implementados pelo V12. Este Server fornece a configuração e a seleção dos recursos correspondentes.

## Como usar

### Adicionar um ícone de competição

Com o FIFA fechado, coloque um PNG (preferencialmente transparente), JPG, WEBP ou BMP em
`data/ui/imgAssets/careerCompetitionIcons/`, dentro da instalação do jogo. Use o **ID da
competição** ou o nome completo cadastrado no `FSW/settings.ini` como nome da imagem:
por exemplo, `1761.png` ou `BRA - Brasileirao Serie A.png` nesta edição. Não é necessário
abrir nem editar o settings.ini. O arquivo `COMPETICOES.txt`, gerado automaticamente na
mesma pasta ao abrir o Server, lista os nomes aceitos para a instalação selecionada.

Abra o Server atualizado e aguarde alguns segundos antes de iniciar o FIFA. O botão de
iniciar o FIFA também conclui a importação antes de abrir o jogo. O Server cria o DDS no
formato e tamanho corretos, resolve o ID visual e atualiza o índice interno. **Não edite
o index.tsv.** O original e os ícones de outras competições ficam preservados. Para trocar
o desenho, substitua a imagem original; não deixe duas imagens da mesma competição.

Imagens colocadas enquanto o FIFA está aberto são processadas quando ele estiver fechado
e o Server estiver aberto. Nomes desconhecidos ou ambíguos e imagens inválidas são
preservados e explicados na aba Logs, sem atribuir um ícone a outra competição.
O Server não identifica competições pelo desenho da imagem e não cria campeonatos.
Competições novas já cadastradas no CompData são descobertas automaticamente; mapeamentos
específicos existentes têm prioridade. `c7.png` é uma alternativa para quem já conhece
o ID visual; `7.png` significa ID de competição, e pode corresponder a outro recurso.

Os backups ficam em `runtime/backups/career_competition_icons/`. Os DDS `c<ID>.dds`
existentes continuam funcionando diretamente com o módulo `career_ui_assets` atualizado.
Esse recurso usa o encoder DDS DXT5 do Pillow (12.1.1 no executável distribuído).

### Iniciar o jogo

1. Abra `Server16Python.exe` e selecione a instalação do FIFA.
2. Deixe o Server aberto e inicie o FIFA 16.
3. No pré-jogo, abra o painel com **F12** ou **Start**, conforme o contexto.
4. Use os cartões de estádio, público e configurações. Confirme em **Aplicar** para salvar.
5. Depois de trocar o executável ou uma DLL, reinicie os programas envolvidos.

As opções de apresentação ficam em `ModCarrerMode/config/match_presentation.ini`. A competição e a fase usam os IDs de `FSW/settings.ini`; o Server valida e seleciona os assets locais em `data/sceneassets/entrance_props/`. A pasta local `runtime/` guarda diagnósticos da sessão.

Os atalhos dos botões começam em **F3**. Configurações, público, estádio e
narração usam **F3 para Aplicar** e **F4 para Voltar/Cancelar**. No áudio,
**F3** aplica o volume geral, **F4** aplica o específico e **F5** cancela.
No menu inicial: **F3** público, **F4** estádio, **F5** configurações,
**F8** narradores e **F9** fechar. **F6/F7** continuam reservados à física.
Os comandos do controle e do mouse permanecem os mesmos. Reinicie o Server
e o FIFA depois de atualizar o executável e a DLL do painel.

A física usa `ModCarrerMode/mods/cloth_motion/cloth_motion.ini`. Desativar
seleciona a física original e mantém a ponte de controle disponível para
reativação durante a mesma partida. Após instalar a atualização 0.8.1 da DLL,
reinicie o FIFA e o Server uma vez. F6 também alterna a física.

Ao fechar o Server, timers, áudio, conexões e mapas de memória são liberados
mesmo se uma etapa falhar. Operações de escrita de estádio/BH terminam antes
da saída; leitores de banco iniciados pelo próprio Server são encerrados.
No executável, o processo sai após a limpeza sem aguardar finalizadores de
bibliotecas que poderiam deixá-lo oculto no Gerenciador de Tarefas. O FIFA e
outros processos não são encerrados. O log registra as etapas de `Shutdown`.

## Executar pelos fontes

Requer Windows, Python 3.10 ou superior e FIFA 16 compatível. Instale as dependências e execute:

```powershell
python -m pip install psutil pillow pygame rarfile pyinstaller pythonnet
python main.py
```

`build_exe.bat` e `Server16Python.spec` preparam o executável. As bibliotecas nativas exigidas pelo build precisam estar em `bin/`; os nomes estão no `.spec`. Um pacote só de código não inclui essas bibliotecas nem os assets de apresentação.

## Organização e testes

- `server16_py/`: aplicativo, painéis e contexto da partida.
- `server16_py/entrance_props_runtime.py`: seleção e validação dos objetos da competição.
- `native_mods/`: fontes das integrações nativas do Server.
- `tests/`: testes sem abrir o FIFA.
- `tools/`: preparação e edição.
- [Roteiro de uso](ROTEIRO_FIFA_FRIENDS.md): instruções detalhadas.

Modelos, texturas, áudio, vídeos, retratos, caches e arquivos pessoais permanecem locais. Uma falha na seleção opcional dos objetos de abertura preserva os outros recursos da partida.

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

`scripts/export_code.py` gera um ZIP de fontes, configurações e documentação sem assets ou executáveis. O ZIP precisa ser compilado antes de usar no jogo.
