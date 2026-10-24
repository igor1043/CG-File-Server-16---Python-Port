# Server16 0.2.15 — compatibilidade e controles

- Com ReShade carregado, o overlay usa os callbacks oficiais da API 17 (`reshade_present` e `destroy_effect_runtime`). Não instala outro hook de `Present` nem cria um dispositivo de sondagem do ReShade.
- Sem ReShade, mantém o caminho COM existente. O desenho seleciona a janela do jogo e recria seus recursos quando o dispositivo muda.
- O hino de gol do mandante e do visitante faz fade ao confirmar que o relógio da partida voltou a avançar, inclusive depois de pular o replay. Pausas conservam a posição do áudio.
- Nova aba **Controles** no Server16 e opção **Configurar controles** no overlay F12, acessível nos menus de estádio, pré-jogo e ajustes da partida.
- Até quatro controles genéricos, perfil automático SDL ou mapeamento guiado de botões, direcionais, analógicos e gatilhos. As calibrações são salvas por GUID em `runtime/settings.json`.
- Controles Xbox/XInput continuam pelo suporte nativo. A ponte virtual é opcional e desativada por padrão. Os instaladores ViGEmBus e HidHide só são executados por uma ação explícita do usuário na tela; nada é instalado ao iniciar o Server.

## Uso

Em **Controles**, escolha o jogador e o dispositivo. Use o perfil automático ou **Mapear botões e analógicos**, deixando os comandos soltos no início. Depois ative a ponte. Se faltar ViGEmBus, use **Instalar driver Xbox virtual** e reinicie o Server16 após a instalação. O HidHide é opcional para evitar entrada dupla do controle físico e virtual; a visibilidade do físico é restaurada ao fechar o Server.

No assistente, F4 pula um comando; os botões físicos A/B são aprendidos e não cancelam o mapeamento. Use o botão Cancelar ou F12 para sair. Os demais menus aceitam teclado, controle e mouse.

## Referências e validação

Ponte de controle adaptada do projeto de Michel: https://github.com/michelMK45/CG-File-Server-16---Python-Port, commit `59d59216379a6184f1835f2a7149197b8e5f599f`. Os módulos da aplicação e o renderer dele não substituem os deste projeto.

Headers ReShade v6.5.1/API 17 em `server16_py/d3d_overlay/third_party/reshade`, com licença original. Cliente vgamepad 0.1.0 fixado em `vendor`, com licença. HidHide 1.5.230.0 obtido da release oficial; origem e hash em `bin/HidHide/SOURCE.json`.

Validação: 254 testes Python, com três opcionais ignorados; renderer D3D11 por software; processo independente com a DLL exata do ReShade 6.5.1, 210 frames, três ciclos de dispositivo e redimensionamento; checagem do executável congelado e dos arquivos embutidos.

Esses testes não reproduzem o driver, os overlays e o hardware do Robson. A estabilidade no computador dele e o mapeamento de um controle genérico físico ainda precisam do teste de uso. ReShade e suas configurações não são alterados por esta versão.

Diagnóstico de build: `Server16Python.exe --server16-selftest caminho-do-relatorio.json` gera um relatório sem abrir a interface, conectar ao jogo ou instalar drivers.
