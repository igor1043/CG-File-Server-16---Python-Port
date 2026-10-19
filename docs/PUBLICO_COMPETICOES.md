# Público estimado por competição

O modo automático passa a usar a competição da próxima partida real do clube,
mesmo quando a tabela selecionada na Central é de outro campeonato. O fator
publicado no card e aplicado pelo controlador de público vem da mesma decisão.

| Competição | Bônus em pontos percentuais | Mínimo antes dos mata-matas |
|---|---:|---:|
| Libertadores | 22 | 75% |
| Sul-Americana | 16 | 70% |
| Recopa | 20 | 78% |
| Outros torneios internacionais | 14 | 68% |
| Brasileirão A | 14 | 68% |
| Brasileirão B | 10 | 60% |
| Copa do Brasil | 16 | 70% |
| Brasileirão C | 8 | 50% |
| Brasileirão D | 6 | 42% |
| Estaduais principais instalados | 7 | 52% |

O bônus substitui o antigo adicional internacional de 6 pontos. Oitavas e quartas
elevam o mínimo em 4 pontos; semifinal, em 8 pontos, com mínimo de 78%. O teto
normal é 88%; finais chegam a 90%, respeitando o limite global configurado.
Assim, a Libertadores tem mínimos de 75%, 79%, 83% e 90% conforme a fase.
Os demais fatores existentes — campanha, fase, forma, rivalidade e reputação —
continuam participando. Torneios de pré-temporada conservam sua estimativa.

A identificação usa a árvore e o identificador de troféu do FCE instalado,
sem confundir o número do objeto do calendário com a identidade do torneio.
Os ajustes ficam na seção `[competition_attendance]` de
`ModCarrerMode/crowd.ini`: `<competição>_bonus_percent`,
`<competição>_minimum_percent` e, opcionalmente, `<competição>_maximum_percent`.
Entradas inválidas usam os valores padrão. O modo manual continua disponível.

O código nativo fica em
`U:\mods\FIFA Friends V12\ModCarrerMode\source\career_native`.
Os testes `test_competition_attendance.cmd`, `test_international_crowd.cmd` e
`test_crowd_next_profile.cmd` verificam os perfis, a escolha da partida real e a
integração do card com o fator aplicado pelo runtime. Não substituem a observação
visual de uma partida no FIFA.

Após atualizar `dinput8.dll` e o Server, feche e abra ambos uma vez para carregar
os novos módulos. A instalação dos arquivos não substitui uma DLL já carregada
na memória do jogo.
