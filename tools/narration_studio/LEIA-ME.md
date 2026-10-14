# FIFA 16 Narration Studio

## Pastas e funcionamento

O jogo procura uma subpasta por narrador em `Narrations/<nome>`. Cada pacote
instalado contém somente `profile.npack`, `profile.json`, `narrator.txt` e,
quando disponível, `portrait.png`. Os bancos BIG originais não são regravados.

O Narration Studio mantém projetos, transcrições, relatórios e cache em
`Narration Studio/Projetos`; o catálogo FIFA e as fontes originais ficam nas
pastas externas do pacote. Na primeira abertura, escolha a pasta do FIFA 16 que
contém `fifa16.exe`. Use **Converter e instalar no jogo** para compilar o
projeto e publicar somente os quatro arquivos consumidos pelo Server16.

O Server16 lê os perfis instalados a partir da própria pasta do executável. O
formato continua sendo `Narrations/<narrador>`, com uma pasta independente para
cada voz. Um arquivo `competition_names.json` opcional pode ficar na raiz de
`Narrations` para nomear competições.

## Conteúdo de um projeto editável

- `project.json`: associações, competições e dados editáveis.
- `transcriptions/`: textos exportados para inspeção e revisão.
- `build/`: pacote compilado, relatório, progresso e cache; fica fora do jogo.
- `portrait.png`: imagem do narrador, copiada para o perfil do jogo ao instalar.

## Compilação

Execute os testes `test_narration*.py` antes de publicar. Para compilar o editor,
use `build_portable_editor.py --worker <EXE> --tools <pasta>`. Para compilar o
Server16, use `Server16Python.spec` com o PyInstaller do ambiente de build.
Binários, gravações, bancos do jogo, catálogos e modelos não devem entrar em
commits.
