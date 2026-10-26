# Sala interna do VAR — experimento adiado em 25/10/2026

O usuário solicitou retirar o código depois que o teste em partida não apresentou a sala. Esta entrega não carrega a DLL, painel, configuração ou assets dessa sala experimental. A cabine já existente à beira do gramado (`var_cabin`) continua independente e preservada.

## Ideia para retomar

Criar um ambiente nativo escondido, três oficiais sentados e monitores, usando recursos da própria engine. Mostrar somente durante cutscenes elegíveis, com opção própria para desligar. Não envolve decidir lances ou mudar regras de arbitragem.

## Evidência do protótipo

O primeiro teste não pediu streaming corretamente. A segunda tentativa também corrigiu colisões de nomes dos recursos. A instrumentação passou a registrar os 11 recursos disponíveis e chamadas nativas de desenho, mas isso não comprovou que a câmera exibiu a sala. O teste visual foi negativo. Antes de reimplementar, investigar elegibilidade da câmera, grafo nativo, transforms e visibilidade sem intervir no agendador MUSE nem executar APIs de cena em threads remotas.

Os fontes e recursos experimentais foram arquivados localmente em `code-release/release_final_20261025/var_room_deferred`, fora da distribuição. A retomada precisa de um teste mínimo de câmera/objeto visível antes de montar a sala completa.
