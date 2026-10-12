Abertura do FIFA 16: o writer nativo em exe+0x3c9a720 consulta o byte +0x18 da estrutura sink. O hook deve inicializar o campo truncated com zero. Uma estrutura de apenas três campos deixa o byte fora do objeto e pode produzir nomes vazios, incluindo data/loc/.db. O crash reproduzido foi exe+0x4b4e1e9 ao carregar o idioma, antes da injeção da narração.

Validação: build MSVC /W4 /WX; teste de formatação por_br e data/loc/por_br.db, seleção de imagens e limites de buffers. Confirmar também a abertura do jogo com a DLL corrigida.
