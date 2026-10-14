# Narration Studio

Editor com duas colunas sincronizadas (original FIFA / narração personalizada)
e uma biblioteca recolhível à direita. Cada coluna tem sua própria busca por
nome, assunto e transcrição. Na biblioteca, é possível anexar pastas, pesquisar
descrições, ouvir, filtrar usados/não usados e aplicar um áudio à ocorrência.
A coluna personalizada tem uma caixa de aprovação por fala; as aprovadas ficam
verdes, são filtráveis e acompanham o projeto salvo.

## Uso portátil

Execute `NarrationStudio.exe` na pasta `Narration Studio`. Na primeira abertura,
escolha a pasta raiz do FIFA 16 (a que contém `fifa16.exe`). O catálogo fica em
`Catálogo Original FIFA 16\Catálogo editável\.studio`, o modelo Whisper em
`Narration Studio\Modelo IA` e os projetos em `Narration Studio\Projetos`.
Mantenha essas quatro pastas lado a lado ao mover o pacote; os caminhos antigos
são atualizados automaticamente. O pacote inclui `bin` com FFmpeg, vgmstream e
EA Sound, além do modelo local, então importar, converter e transcrever não
exigem downloads separados.

Se executar o editor fora do pacote, ele também pode ficar ao lado de
`fifa16.exe`. A configuração salva em `studio_config.json` aceita caminhos
relativos à própria pasta do arquivo ou caminhos absolutos. O jogo mantém uma
pasta por narrador em `Narrations/<narrador>` com apenas `profile.npack`,
`profile.json`, `narrator.txt` e `portrait.png`. O projeto editável, textos,
relatórios e cache de conversão ficam em `Narration Studio\Projetos`, fora do
jogo. O catálogo e os áudios base ficam nas pastas próprias do pacote. Pastas de
biblioteca anexadas conservam os arquivos no local escolhido. Anexar uma pasta examina todos os
níveis de subpastas e lista arquivos WAV, MP3, FLAC, OGG e M4A. Transcrever a
biblioteca produz arquivos `<audio.ext>.txt` ao lado de cada áudio e um
`transcriptions.json` com todas as faixas em cada pasta anexada.
Processamento e consultas ocorrem fora da interface.

Falas não associadas continuam usando o original. A conversão conserva a
duração da gravação e verifica o áudio SPS gerado. IDs do PES não são IDs do
FIFA: a associação depende do conteúdo e precisa de revisão.

## Compilação

Para compilar, use Python com Pillow e PyInstaller para o editor e as dependências
faster-whisper, ctranslate2, PyAV e NumPy para `TranscriptionWorker.spec`. Depois
execute `build_portable_editor.py --worker <EXE> --tools <pasta>`. O pacote final
também precisa da pasta local do modelo Whisper; o script de distribuição inclui
esse modelo junto dos áudios base. Binários e modelos não são versionados.

`pes_index_all.py` inventaria a biblioteca PES de referência.
`pes_extract_library.py extract` extrai arquivos FLAC completos e verifica as
amostras. `transcribe` transcreve de maneira retomável; `publish` atualiza as
pastas por narrador, índices e textos. `--root` define a pasta de saída.
Arquivos idênticos usam hard links NTFS para evitar duplicação física.

Áudios, bancos do jogo, modelos, catálogos, transcrições e builds não devem ser
incluídos em commits. Execute os testes `test_narration*.py` antes de publicar.
