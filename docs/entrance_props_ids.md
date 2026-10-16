# Entrada 3D por ID de competição — revisão 20

O Server16 identifica a competição (`TOURNAME`) e a fase (`TOURROUNDID`) da partida. O arquivo `U:\fifa 16\FSW\settings.ini`, sincronizado do INI da atualização, fornece os IDs aceitos nas seções `[movies]`, `[Scoreboard]` e `[comp]`. Os nomes de vídeo, placar e estádio não são usados como caminhos de modelos.

Os pacotes ficam em `data/sceneassets/entrance_props/competitions/<ID>/`, tanto no jogo quanto em `U:\mods\FIFA Friends V12`. O TXT `REFERENCIA_IDS.txt` lista os IDs e os nomes exatos do INI para consulta. Esse TXT não participa da seleção.

A fase tem prioridade quando seu ID está no INI e sua pasta contém `asset.ini`. Sem pacote próprio para a fase, utiliza-se a pasta da competição principal, desde que seu ID esteja no INI. Uma pasta reservada e vazia pode receber um pacote convertido posteriormente. Sem pacote, os objetos deste mod não são carregados. O ID 0 é excluído; não há associação por intervalo, nome ou mapa externo.

Em amistosos, sem competição/fase, dois clubes da mesma liga usam a entrada dessa liga. O Server16 consulta `leagueteamlinks` no banco instalado e encontra o nó da competição em `compobj.txt`: por exemplo, liga `7` → objeto `C7` → nó `1738` → pasta `competitions/1738`. O nó precisa existir no `settings.ini`. Ligas diferentes, informações ausentes, liga sem nó único ou pacote ausente ficam sem entrada. Uma competição real, incluindo uma copa sem modelo, nunca é substituída pela liga dos clubes. Essa regra não habilita a cabine do VAR.

Cada pacote contém `model.rx3`, `template.rx3` e `asset.ini`. A DLL mantém a validação nativa de tamanhos, SHA-256, malha, textura e posições dos escudos. Um pacote explícito inválido é recusado. O cache dos emblemas de mandante/visitante é gerado em `fixtures/` dentro da pasta numérica selecionada.

Exemplos: Série A em `1738`, Série B em `1741`, Série C em `1747`, Série D em `1757`, Champions em `195`; a final da Champions usa `245`, presente em `[comp]`. Uma fase sem ID próprio no INI utiliza o pacote principal. Nomes diferentes em `[movies]` e `[Scoreboard] permanecem como escritos no arquivo original.

O botão de objetos de abertura continua usando `[match] entrance_props` de `ModCarrerMode/config/match_presentation.ini`. Essa opção habilita/desabilita a exibição; não redireciona competições. O JSON `runtime/entrance_props_selection.json` é diagnóstico da seleção preparada pelo Server16, não uma regra editável.

O carregador Python usa o mesmo `SessionIniFile` do Server16. A DLL consulta os mesmos IDs do INI e confirma o contexto da partida antes de solicitar os RX3s. Para amistosos, `runtime/entrance_props_context.ini` transmite automaticamente a seleção do Server16. Não é um arquivo de configuração: não deve ser editado ou distribuído. A DLL exige o mesmo processo FIFA, arquivo posterior à abertura do processo, os dois clubes atuais e ausência de competição/fase. A seleção é invalidada ao limpar o contexto e recalculada se o banco terminar de carregar depois da leitura dos times. Não consulta `entrance_competitions.ini`, catálogos de conversão, relatórios JSON ou o TXT de referência.

Os pacotes antigos com nomes, variantes não selecionadas, imagens e relatórios foram preservados em `ModCarrerMode/backups/entrance_ids_settings_20261014/competitions_original` em cada raiz. O mapa antigo fica nesse mesmo backup. Ferramentas e manifesto da migração ficam em `J:\mods\fifa 16\estudos fifa 16\42_ENTRADA_IDS_SETTINGS_20261014`.

Validação: testes Python de prioridade/herança por fase, INI como fonte exclusiva, IDs inválidos, corrupção, botão e continuidade dos outros recursos; testes de amistoso na mesma liga, ligas diferentes, copa com os mesmos clubes, banco atrasado, invalidação e correspondência única em compobj; testes nativos de seleção, apresentação e transparência, com contexto de outro processo, clubes diferentes e arquivo antigo recusados; compilação MSVC `/W4 /WX`. Reiniciar o FIFA e o Server16 carrega os executáveis e a DLL novos. A confirmação visual da abertura deve ser feita no jogo.
