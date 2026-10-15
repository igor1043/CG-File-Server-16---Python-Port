# FIFA 16 Narration Studio

Na primeira abertura, selecione a pasta que contém fifa16.exe. Depois escolha
um narrador existente ou crie outro. O editor tem três colunas: referência
original, sua narração e biblioteca de áudios do narrador ativo.

## O que copiar para o jogo

Copie a pasta Narrations de “Coloque no FIFA 16” para a raiz que contém
fifa16.exe, mesclando as subpastas. O Server16 atualizado carrega os perfis
dessa pasta do jogo. A cópia em “Coloque no FIFA 16” serve para distribuição;
ela não é consultada durante a partida nem se atualiza sozinha após edições.

Cada narrador tem profile.json, narrator.txt e profile.npack, além da foto
quando disponível. profile.npack é o pacote de áudio do mod, não um vídeo MP4
nem um ZIP para extrair. Ele reúne os áudios convertidos e as associações às
falas do FIFA; gravações reutilizadas são guardadas uma vez. Preserve o nome
e a extensão. A pasta Studio contém os dados de edição e áudios importados.
Outras pastas de trabalho, como encoded, não substituem o pacote de reprodução.
O perfil Tiago Leifert usa os bancos originais já instalados no FIFA.

## Editar e ouvir

As transcrições são salvas automaticamente enquanto você digita nas três
colunas. Para comparar as gravações, selecione uma ocorrência e use o player
de cada coluna. Os filtros de ocorrência e situação mantêm as duas primeiras
listas alinhadas; os navegadores mostram a página atual e o total de páginas.
As três listas começam pela coluna “Nº”. Original e sua narração usam a mesma
numeração; a biblioteca numera seus próprios áudios. A sequência continua nas
páginas seguintes e acompanha a lista filtrada. Na lista central, o texto fica
ao lado da aprovação; o nome do arquivo aparece nos detalhes do player.

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
