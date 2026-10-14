# Narration Studio

Editor de três colunas para o FIFA 16: áudio original, narração personalizada
e biblioteca de assets. Veja LEIA-ME.md para o fluxo de uso.

O pacote distribuído tem três pastas principais: Narration Studio,
Coloque no FIFA 16 e Áudios Originais dos Narradores. Na primeira abertura,
o EXE solicita a pasta do jogo. Essa escolha fica na configuração local do Windows.
O catálogo e o modelo Whisper ficam junto do Studio.

Cada narrador tem seu diretório Narrations/<narrador> no jogo. As gravações
importadas ou utilizadas ficam em Studio/assets, e o projeto editável é salvo
em Studio. Atribuir um áudio atualiza automaticamente os slots afetados do
profile.npack, preservando os demais. Falhas na codificação preservam a
atribuição anterior. As transcrições e classificações manuais são salvas durante
a edição; transcrever novamente conserva o estilo escolhido pelo usuário.

Para compilar, use o ambiente Python do projeto com PyInstaller. Compile
TranscriptionWorker.spec e então build_portable_editor.py --worker <EXE>
--tools <pasta>. O modelo local Whisper acompanha a distribuição.
O diretório portátil bin/encoder contém EA Sound e suas DLLs; bin contém
vgmstream e suas DLLs. Essas bibliotecas não podem ser misturadas.

pes_index_all.py inventaria os arquivos PES. pes_extract_library.py extract
extrai FLAC completos; transcribe e publish produzem o acervo de referência.
IDs do PES e do FIFA são diferentes: a associação precisa considerar o conteúdo.

Execute test_narration*.py antes de publicar. Áudios, catálogos, bancos,
transcrições de referência, modelos e binários não são versionados.
