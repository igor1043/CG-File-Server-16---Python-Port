# Entrada 3D por ID de competição — revisão 19

O Server16 identifica a competição (`TOURNAME`) e a fase (`TOURROUNDID`) da partida. O arquivo original `U:\fifa 16\FSW\settings.ini` fornece os IDs aceitos nas seções `[movies]`, `[Scoreboard]` e `[comp]`. Os nomes de vídeo, placar e estádio não são usados como caminhos de modelos.

Os pacotes ficam em `data/sceneassets/entrance_props/competitions/<ID>/`, tanto no jogo quanto em `U:\mods\FIFA Friends V12`. O TXT `REFERENCIA_IDS.txt` lista os IDs e os nomes exatos do INI para consulta. Esse TXT não participa da seleção.

A fase tem prioridade quando seu ID está no INI e sua pasta contém `asset.ini`. Sem pacote próprio para a fase, utiliza-se a pasta da competição principal, desde que seu ID esteja no INI. Uma pasta reservada e vazia pode receber um pacote convertido posteriormente. Sem pacote, os objetos deste mod não são carregados. O ID 0 é excluído; não há associação por intervalo, nome, clube ou mapa externo.

Cada pacote contém `model.rx3`, `template.rx3` e `asset.ini`. A DLL mantém a validação nativa de tamanhos, SHA-256, malha, textura e posições dos escudos. Um pacote explícito inválido é recusado. O cache dos emblemas de mandante/visitante é gerado em `fixtures/` dentro da pasta numérica selecionada.

Exemplos: Série A em `1615`, Série B em `1618`, Champions em `195`; a final da Champions usa `245`, presente em `[comp]`. Uma fase sem ID próprio no INI utiliza o pacote principal. Nomes diferentes em `[movies]` e `[Scoreboard] permanecem como escritos no arquivo original.

O botão de objetos de abertura continua usando `[match] entrance_props` de `ModCarrerMode/config/match_presentation.ini`. Essa opção habilita/desabilita a exibição; não redireciona competições. O JSON `runtime/entrance_props_selection.json` é diagnóstico da seleção preparada pelo Server16, não uma regra editável.

O carregador Python usa o mesmo `SessionIniFile` do Server16. A DLL consulta os mesmos IDs do INI e confirma o contexto da partida antes de solicitar os RX3s. Não consulta `entrance_competitions.ini`, catálogos de conversão, relatórios JSON ou o TXT de referência.

Os pacotes antigos com nomes, variantes não selecionadas, imagens e relatórios foram preservados em `ModCarrerMode/backups/entrance_ids_settings_20261014/competitions_original` em cada raiz. O mapa antigo fica nesse mesmo backup. Ferramentas e manifesto da migração ficam em `J:\mods\fifa 16\estudos fifa 16\42_ENTRADA_IDS_SETTINGS_20261014`.

Validação: testes Python de prioridade/herança por fase, INI como fonte exclusiva, IDs inválidos, corrupção, botão e continuidade dos outros recursos; testes nativos de seleção, apresentação e transparência; compilação MSVC `/W4 /WX`; auditoria nativa dos pacotes instalados. Reiniciar o FIFA e o Server16 carrega os executáveis e a DLL novos. A confirmação visual da abertura deve ser feita no jogo.
