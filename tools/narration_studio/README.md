# Narration Studio

Editor com duas colunas sincronizadas (original FIFA / narração personalizada)
e uma biblioteca recolhível à direita. A biblioteca permite anexar pastas,
buscar nomes e transcrições, ouvir, filtrar usados/não usados e aplicar um áudio
à ocorrência selecionada. O contador de usos considera o projeto atual.

## Uso

Coloque `NarrationStudio.exe` junto de `fifa16.exe`. Ele descobre `Narrations`
automaticamente. Projetos e pacotes ficam em `Narrations/<narrador>`; o catálogo
editável, áudios originais decodificados e cache ficam em `Narrations/.studio`.
Pastas anexadas conservam seus arquivos no local escolhido. Transcrever a
biblioteca produz arquivos `<audio.ext>.txt` e um `transcriptions.json` em cada
pasta anexada; também salva o índice no projeto. O modelo de IA é local após
seu primeiro download. Processamento e consultas ocorrem fora da interface.

Falas não associadas continuam usando o original. A conversão conserva a
duração da gravação e verifica o áudio SPS gerado. IDs do PES não são IDs do
FIFA: a associação depende do conteúdo e precisa de revisão.

## Compilação

O editor usa Python, Pillow e PyInstaller. O processo de IA usa faster-whisper,
ctranslate2, PyAV e NumPy. Compile `TranscriptionWorker.spec` no diretório deste
arquivo. Depois execute `build_portable_editor.py --worker <EXE> --tools <pasta>`
com Python 3.10/PyInstaller. A pasta de ferramentas deve conter `bin` com
ffmpeg, vgmstream-cli, EA Sound e suas dependências. O resultado reúne esses
componentes em um EXE. Binários de terceiros e seus modelos não são versionados.

`pes_index_all.py` inventaria a biblioteca PES de referência.
`pes_extract_library.py extract` extrai arquivos FLAC completos e verifica as
amostras. `transcribe` transcreve de maneira retomável; `publish` atualiza as
pastas por narrador, índices e textos. `--root` define a pasta de saída.
Arquivos idênticos usam hard links NTFS para evitar duplicação física.

Áudios, bancos do jogo, modelos, catálogos, transcrições e builds não devem ser
incluídos em commits. Execute os testes `test_narration*.py` antes de publicar.
