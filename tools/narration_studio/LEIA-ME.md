# FIFA 16 Narration Studio

Na primeira abertura, selecione a pasta que contém fifa16.exe. Depois escolha
um narrador existente ou crie outro. O editor tem três colunas: referência
original, sua narração e biblioteca de áudios do narrador ativo.

As transcrições são salvas automaticamente enquanto você digita nas três
colunas. Para comparar as gravações, selecione uma ocorrência e use o player
de cada coluna. Os filtros de ocorrência e situação mantêm as duas primeiras
listas alinhadas; os navegadores mostram a página atual e o total de páginas.

Na biblioteca, “Importar pasta inteira” copia WAV, MP3, FLAC, OGG e M4A,
inclusive subpastas, para <FIFA>\Narrations\<narrador>\Studio\assets.
O campo “Estilo” da importação permite classificar a pasta inteira. Deixe
“(automático)” para usar a classificação baseada nas informações de cada áudio.

Selecione um asset para ouvir e editar sua transcrição. Em “Estilo deste áudio”,
escolha uma categoria ou digite outra; a alteração é salva automaticamente.
Você também pode filtrar, ordenar e agrupar a biblioteca por estilo.
“Transcrever selecionado” processa um único áudio; “Transcrever pendentes”
processa os que ainda não têm texto. A IA utiliza o modelo local incluído no pacote.

Para substituir uma fala, selecione a ocorrência na coluna do meio e o asset
na biblioteca; clique em “Aplicar à fala selecionada”. Também é possível
importar um arquivo diretamente na ocorrência. O Studio copia a gravação
completa para a pasta do narrador no jogo, converte e atualiza seu profile.npack
em segundo plano. Não há etapa manual de gerar ou instalar. Se ocorrer uma
falha de conversão, a atribuição anterior é preservada e o erro é exibido.

“Restaurar áudio original” remove a substituição e atualiza o pacote do jogo.
“Remover” na biblioteca pede confirmação e informa o efeito nas associações.
Arquivos físicos são apagados apenas quando pertencem à pasta gerenciada
daquele narrador; as gravações externas originais são preservadas.

Os dados editáveis ficam em <FIFA>\Narrations\<narrador>\Studio e também em
Narration Studio\Projetos. Os áudios de referência externos continuam em
Áudios Originais dos Narradores. Para usar a narração atualizada, selecione
ou reaplique o narrador na prévia pelo Server16. Uma partida em andamento
continua usando o pacote que já foi carregado em memória.

## Compilação

Execute os testes test_narration*.py. Compile TranscriptionWorker.spec,
depois build_portable_editor.py --worker <EXE> --tools <pasta>.
As DLLs do EA Sound devem ficar em bin/encoder; o vgmstream usa as próprias
DLLs em bin. Gravações, bancos, catálogos, modelos e builds não entram em commits.
