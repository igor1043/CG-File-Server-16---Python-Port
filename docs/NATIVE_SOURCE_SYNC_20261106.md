# Fontes nativas e correções de 06/11/2026

O núcleo em `native_mods/career_native` e suas dependências locais estão
sincronizados com a versão instalada do FIFA Friends V12. Inclui os fontes,
recursos binários de código, scripts e testes que faltavam à cópia parcial.
O cabeçalho compartilhado fica em `native_mods/common`, como os includes exigem.

O frontend publica o trabalho na thread da interface para concluir a troca de
estádio depois de sair da carreira. A DLL externa `bin/frontend_stadium.dll`
corresponde ao módulo instalado no jogo. O executável 0.2.21 não precisou de
novo build: ele não embarca esse plugin, o núcleo do FIFA nem a DB.

A DB e o validador de CRC estão na branch `fifa-friends-v12` de
[fifa-mods](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12).
A correção restaura 32 bytes auxiliares de checksum sem alterar os registros
válidos das 137 tabelas. Três aberturas controladas chegaram a PressStart e o
usuário confirmou o funcionamento. A ordem de inicialização anterior permanece.

Testes: frontend owner, fila do fundo e preflight do núcleo; 30 testes Python
de frontend/mascote, 13 do rodapé e quatro de CRC. Saves/SQL pessoais não são
distribuídos. A causa do dump antigo da instalação de referência em +0x3A41F43 não foi demonstrada
como sendo a mesma da falha reproduzida da DB em +0x4B6CB75.
