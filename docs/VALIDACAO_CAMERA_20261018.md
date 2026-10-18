# Validação das câmeras do Server16 — 18/10/2026

A câmera Profissional do FIFA serve de base para Primeira pessoa e Terceira pessoa · carreira.
Ativação, modo, FOV de cada modo e distância da terceira pessoa ficam salvos no Server.
Padrão solicitado: 85 graus nos dois modos, suavização Forte e Campo e bola fixos.
A primeira pessoa não amplia a lente automaticamente ao ganhar posse.

Terceira pessoa: Perto (4,80 m atrás / 2,30 m acima), Intermediária (7,50 / 3,20 m)
e Afastada (11,50 / 4,50 m), com transição suavizada e lente moderada (60–90 graus).
Primeira pessoa: FOV ajustável entre 75 e 120 graus; segue a cabeça com folga contra cabelo.

DLL de produção: bin/server16_first_person_v5.dll, embutida no Server.
Canal: Local\FIFA16_FirstPersonCamera_v4, versão 4, 80 bytes.
Preferências JSON versão 4: enabled, mode, distance, fov_first_person, fov_career.
A migração mantém ativação/modo e aplica 85 graus nos dois modos. F10 salva desligado;
fechar o Server ou trocar o processo do FIFA preserva a preferência de ativação.

O acompanhamento aceita KickOff (2), OutOfPlay (14) e Play (15), com pose válida,
fresca e vinculada ao mesmo GameData. Em 2/14 a âncora é imediata. Troca de jogador,
fase, modo, contexto ou pose descontínua reinicia os filtros. O cache nativo de pose
(+BE0, 0x64 bytes, copiado em 8AB29..8ABC8 e usado pela interpolação em 8AAE7)
também recebe a pose de primeira pessoa para evitar divergência nas transições.

Verificações: 297 testes Python aprovados. Testes nativos com /W4 /WX aprovados:
visibilidade de bola/corpo, lente estável, três distâncias e transição, translação
sem arrasto, suavização de órbita, proteção do cabelo, fases e protocolo real isolado.
O enquadramento final e o comportamento após gol/cobranças precisam da avaliação em partida;
os testes matemáticos não substituem essa conferência. Não há colisão com o cenário.

A aplicação de estádio conserva a escolha ao voltar da prévia e bloqueia novas
publicações após sair do pré-jogo, revertendo aplicações pendentes sem trocar o ID.
A corrida de reaplicação tardia foi reproduzida nos logs; o sintoma de textura verde
precisa de conferência visual após a correção.
