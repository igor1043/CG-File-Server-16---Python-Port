# Cenas extras: técnico e mascote — revisão 12

Renderização nativa do FIFA 16, timestamp 577DE45C. O enquadramento foi confirmado em RAM na revisão 10; esta revisão mantém o mesmo callback e oferece cinco tomadas frontais por perfil, sorteio normal e continuidade da tomada. Câmera plantada, com pan limitado, sem órbita pelas costas.

## Frequência e duração

- 40% de chance por parada elegível, um único sorteio por parada.
- Intervalo mínimo de 10 segundos reais após terminar a tomada anterior. Não significa uma cena a cada 10 segundos: precisa existir uma nova cutscene compatível e passar pelo sorteio.
- Pesos iguais (1:1) para técnico e mascote quando ambos estão disponíveis. Os pesos dividem a seleção entre personagens; a chance controla a frequência total.
- O personagem selecionado permanece nos fragmentos compatíveis da mesma sequência nativa, inclusive na transição para a reação `emotion`. A troca de grafo ou o antigo limite artificial de 5 segundos não interrompem mais essa tomada para mostrar o jogador reclamando.
- O FIFA continua dono da duração e da retomada. Ao voltar à partida, entrar em replay, menu ou cena incompatível, a câmera é liberada. O mod não estica a parada além da janela nativa e respeita o usuário pulando a cena.

`test_mode=0` é o padrão distribuído. Teste manual precisa ser ativado explicitamente e respeita as mesmas proteções.

## Proteção da engine

Somente o frame reservado do BCEngine é alterado no callback anterior à publicação atômica (slot 113358 / função 5D420). Visibilidade, LOD e desenho recebem a mesma câmera. GetFrame, Play e Update permanecem originais. A fila MUSE é somente consultada: sem Queue, Skip, Clone, Release ou LoadXML. Os experimentos antigos que chamavam o agendador não devem ser reinstalados.

Início permitido em cutscenes nativas reconhecidas de lateral e reações de chute para fora/tiro de meta/escanteio. Gameplay, replay, menus e bola parada sem cutscene são recusados. As poses vêm de `Fifa16ReadSceneActors v1`, em `mascot_goal_line.dll`, com identidade, estabilidade e atualidade verificadas. Esses critérios não comprovam residência de texturas na GPU.

## Arquivos e testes

DLL: `ModCarrerMode/mods/extra_scenes/extra_scenes.dll`. INI: `ModCarrerMode/config/extra_scenes.ini`, relido a cada 250 ms. Server16 0.2.18 oferece controles separados para técnico e mascote em Cenas extras, antes e durante a partida.

`build_extra_scenes.cmd` compila com `/W4 /WX` e testa frames privados/publicados, preservação de metadados/aspecto, regras de cutscene, continuidade, variações frontais, pesos, sorteio, estabilidade e liberação ao voltar ao gameplay. O novo tempo de permanência ainda requer conferência visual após reiniciar.

Diagnóstico: `runtime/extra_scenes_status.ini` (`revision=12`) e `ModCarrerMode/logs/extra_scenes.log`. `FRONTAL_VARIANT` identifica o ângulo e `CUT_VISIBLE_MS` informa a duração observada.
