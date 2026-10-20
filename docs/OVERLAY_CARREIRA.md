# Overlay do modo carreira

Abra no hub da carreira com **Select + Start** ou **F12**. Este é um painel próprio;
os painéis de partida e pré-jogo continuam disponíveis nos seus contextos.

A Central usa internamente `game/screens/fluxHub/FluxHub`, o mesmo identificador
do menu principal e da pausa. Nessa página o gatilho exige leitura válida do
serviço nativo de carreira, usuário/clube ativo e sinal de partida desligado.
As leituras usam os acessores do perfil compatível, verificados antes de seguir
os ponteiros; layout desconhecido ou leitura incompleta não habilita a overlay.
Torneios identificados e pausa de partida continuam separados. A saída para o
menu principal também exige confirmação do fim do contexto antes de gravar.

A ponte nativa reconecta o canal se o Server for reaberto. Uma versão diferente
da DLL já carregada exige reiniciar o FIFA; o Server não instala outro gancho
de renderização sobre a versão antiga.

1. Salve o progresso no FIFA antes de confirmar um pedido.
2. Abra a overlay. A carreira em execução é identificada automaticamente.
3. Escolha **Transferir para outro clube**, **Finanças > Solicitar verba** ou **Aposentadoria**.
   País, liga e time aparecem um abaixo do outro, cada um com ícone e nome.
   Use as setas de cada linha ou esquerda/direita no controle para trocar.
4. Revise e confirme. A confirmação começa com **Voltar** selecionado.
5. Para treinador, feche o painel e permaneça na **Central da Carreira**, sem
   entrar no Calendário nem avançar dias. Aguarde em tempo real: o módulo entrega uma
   **proposta do clube escolhido**, com salário e mensagem criados pelo FIFA.
   O alerta visual/sonoro confirma a proposta somente após verificar os campos
   nativos e encaminhar a entrada **EnterJobOfferSign** ao controlador nativo.
   O FIFA recebe o pedido para abrir sua tela de contrato, com as ações nativas
   de aceitar ou recusar. A abertura não assina automaticamente nem troca o clube.
   Não é necessário se candidatar em Vagas em potencial ou sair da carreira.
6. Finanças, aposentadoria e transferência de jogador seguem a aplicação no save: saia da
   carreira **sem salvar novamente**, aguarde **Aplicado com backup** no menu
   principal e carregue o mesmo slot.

Nos pedidos aplicados no arquivo, é possível cancelar antes da aplicação. Se salvar novamente após
confirmar, o Server recusa sobrescrever esse progresso; cancele o pedido e aguarde
a atualização automática antes de refazê-lo. Durante a preparação, aguarde no menu principal.

Não existe seleção manual de save neste painel. A ponte nativa registra o arquivo
`DATA` que o FIFA leu por completo ao carregar a carreira ou gravou ao salvar.
Prévias da lista de saves e Configurações Pessoais não substituem esse registro.
O Server confere PID, criação do processo, tipo do arquivo e usuário/clube da RAM.
Não escolhe o arquivo mais recente. Ao trocar de carreira ou salvar em outro slot,
a leitura é atualizada e uma confirmação antiga exige nova revisão.

As telas abrem mesmo durante a identificação. A confirmação só fica disponível
depois da leitura da carreira. Caso apareça “Aguardando a carreira em execução”,
salve o progresso ou reabra a carreira após carregar os módulos atualizados.

## Clubes e finanças

Os países/regiões vêm da tabela `nations` instalada. Ligas, divisões, clubes e seus
vínculos são lidos da **carreira em execução**, acompanhando promoções e rebaixamentos.
As regiões adicionais do patch aparecem com os nomes existentes na base. Não há
lista fixa de clubes nem inferência de estados a partir dos nomes dos times.
O escudo usa os recursos já disponíveis ao Server.

A troca funciona para treinador e jogador. Na carreira de jogador, atualiza o
vínculo do elenco, camisa sem conflito, contratos existentes, clube anterior e
escalações salvas. Mantém o vínculo da seleção nacional. Empréstimos ativos,
elencos cheios e layouts incompatíveis são recusados com a razão no painel.
Na carreira de treinador, a mudança de clube depende de você aceitar a proposta
no FIFA. Cada novo pedido **substitui a proposta ou candidatura anterior**.
O destino é validado antes da substituição; o FIFA arquiva a mensagem anterior
pela mesma rotina nativa usada ao trocar de candidatura. O novo pedido cancela
a resposta pendente anterior e entrega somente a proposta do clube escolhido.
O prazo nativo aparece no aviso de sucesso (3 dias de jogo na carreira observada).
Abra a mensagem e assine antes de avançar esses dias. Não é necessário simular
datas para a proposta chegar. Propostas recusadas/expiradas não são recriadas
a partir do histórico.

A solicitação de verba está disponível na carreira de **treinador** e adiciona
o valor ao orçamento de transferências atual, na unidade monetária do save.
É possível digitar pelo teclado ou pelo teclado numérico da overlay com o controle.
Pedidos válidos são aceitos; o orçamento resultante é limitado a 2 bilhões.
A regra é a mesma dos antigos cards de 10 e 100 milhões: adicionar ao orçamento
de transferências. Não cria dívida, juros ou empréstimo de jogador. Os quatro
subcards antigos de verba e aposentadoria foram retirados de Configurações;
essas ações ficam no painel do Server16. A opção normal de Configurações continua disponível.

## Aposentadoria e carregamento

Uso no jogo:

1. Salve normalmente o progresso da carreira antes de abrir o painel.
2. Na Central, aperte F12 ou Select + Start, entre em Aposentadoria, escolha a
   regra e confirme. Não é necessário escolher um arquivo: é o save aberto.
3. Quando aparecer a orientação para sair, feche o painel e saia da carreira
   para o menu principal do FIFA, sem salvar novamente. Não precisa esperar
   um prazo dentro da carreira nem avançar o calendário.
4. Deixe o Server16 aberto e permaneça no menu principal. O aviso de aguarde
   continua visível durante a preparação e aplicação. A rotina confirma a saída
   por dois segundos antes de começar; o restante do tempo depende do save.
5. Só reabra o mesmo slot depois da confirmação de aplicação com sucesso.
   Essa confirmação dura cinco segundos. Se ocorrer erro, a mensagem informa
   que o pedido não foi aplicado; não considere o pedido concluído.

Salvar novamente entre a confirmação e a aplicação altera a versão do arquivo;
o Server recusa substituir essa versão. Nesse caso, cancele e refaça o pedido.

**Remover aposentadoria** limpa `isretiring` dos jogadores marcados, sem alterar
suas idades. **Remover e rejuvenescer** também redefine a idade desses mesmos
jogadores usando a data do calendário da carreira e preservando dia/mês do
aniversário, incluindo o ajuste de 29 de fevereiro. A idade vem de `target_age`
em `ModCarrerMode/config/career_retirement_background.ini`, com padrão de 18 anos
e intervalo seguro de 12 a 50. Jogadores sem aposentadoria marcada permanecem iguais.
As regras foram comparadas com o editor nativo dos cards em cópias do save.
O aviso final informa quantos jogadores foram alterados. Repetir a ação sem
novos jogadores em aposentadoria não altera o arquivo.

O catálogo começa a carregar assim que o Server conecta à RAM, ainda no menu.
Ao entrar na carreira, a inspeção roda em paralelo, antes de abrir a overlay.
O leitor `career_read.py` lê diretamente apenas as tabelas necessárias dos DB v8,
com os nomes e intervalos definidos no metadata instalado. Cada nova versão do
save é relida; não reutiliza orçamento ou clube de uma inspeção antiga. O vínculo
com processo, arquivo e perfil da RAM continua obrigatório antes de confirmar.
Layouts desconhecidos usam a ponte anterior. O editor x86 continua responsável
por toda preparação e validação antes da gravação. Os tempos de cada tarefa
ficam no log do Server como `Career catalog`, `Career inspect` e `Career prepare`.

Depois de assinar com outro clube, o clube ativo é atualizado pela RAM. Enquanto
o FIFA ainda não salvou essa troca, o painel mantém o catálogo já lido e não
reinicia a inspeção do mesmo arquivo. O orçamento antigo fica oculto; finanças
e aposentadoria pedem que o progresso seja salvo antes de confirmar. Ao salvar,
a nova versão do arquivo é lida uma vez e o orçamento correto passa a aparecer.
Propostas de treinador continuam usando o clube ativo da RAM nesse intervalo.
Uma revisão de pedido aberta antes da troca exige nova confirmação.

## Integridade e arquivos

Suporta o contêiner FIFA 16 de carreira `DATA` + `INDEX` com três bancos DB v8.
Formatos diferentes são recusados. A proposta de treinador é entregue em memória
após a atualização normal do motor da carreira, no thread nativo responsável.
O módulo v4 registra um callback no host existente; não instala ganchos adicionais
nas chamadas do jogo. A entrega depende do modelo estável, da Central visível,
do sinal de partida desligado e do contexto de carreira confirmado. Não altera
BrowseJobs, ApplyJob ou geração de vagas nem reenvia a proposta a cada atualização.
Se o menu estiver ocupado, aguarda sem duplicar o e-mail. Troca de carreira ou
pedido com mais de 90 segundos cancela a entrada pendente do contrato.
O FIFA serializa a proposta ao salvar normalmente. A confirmação do Server não
grava o DATA diretamente nesse fluxo.
Utiliza a página que o Server lê na RAM para distinguir carreira, partida e saída.
Página vazia ou desconhecida não autoriza aplicação enquanto o jogo está conectado.

O trabalho x86 é isolado em `career_save_worker.py` com a `FifaLibrary16.dll`
existente. Cada campo inteiro passa por validação do layout e do valor original;
a edição preserva os tamanhos dos blocos e recalcula os CRCs dos bancos e do DATA.
O resultado é reaberto e conferido antes de publicar. O INDEX permanece idêntico.
A apresentação dos avisos temporários usa um cartão branco, texto escuro,
detalhes azuis e cantos arredondados, tanto no FIFA quanto no aviso alternativo
do Server. O aviso continua sem capturar o foco e fecha automaticamente em no máximo 5 segundos.
Finanças e aposentadoria têm uma exceção: a orientação para sair e o aviso de
aplicação permanecem visíveis enquanto o pedido estiver pendente. A confirmação
de sucesso só substitui esse aviso após gravar e verificar o save, e dura cinco
segundos. Falha ou cancelamento também encerram o aviso contínuo. Se o FIFA for
fechado durante a preparação, o Server mantém a orientação no aviso alternativo.
Repetir o mesmo aviso temporário ainda visível não reinicia esse prazo. A mensagem curta
de proposta confirmada aparece uma vez por pedido atual, após a confirmação
nativa da proposta e da entrada do contrato. Reabrir o painel ou carregar um
pedido antigo do save não repete o aviso genérico de proposta recebida.
A publicação exige o fingerprint confirmado e bloqueio exclusivo do arquivo no Windows.
Falha na gravação tenta restaurar o conteúdo anterior pelo mesmo handle.

Pedidos e recibos: `runtime/career_overlay/`. Backups com DATA e INDEX originais:
`runtime/career_overlay/backups/<slot>_<dataUTC>/`. Para restaurar um backup,
feche o FIFA e copie os dois arquivos para o slot registrado em `receipt.json`.

## Validação e build

Na aba Central, as páginas de transferências mais caras e últimas transferências
mostram até dez negócios cada, em duas colunas de cinco. Os componentes originais
TransferInfo continuam mostrando os nomes, escudos, clubes de origem/destino e
valores calculados pelo FIFA. A ponte amplia apenas o limite de publicação de
três para dez, mantendo os filtros e a ordenação nativa. Quando houver menos
negócios elegíveis, somente os registros existentes são publicados.

O seletor de transferência exclui seleções, agentes livres e ligas identificadas
como divisão de acesso. As Séries A, B, C e D continuam disponíveis. A divisão
atual da carreira prevalece: um clube promovido da divisão de acesso permanece
elegível quando já está na Série D do save.

Enquanto o menu ou um de seus submenus estiver aberto, a ponte captura teclado,
mouse e controle nas interfaces DirectInput ANSI/Unicode e XInput, além das
mensagens da janela principal e da janela de renderização. Ao fechar, os botões
pressionados precisam ser soltos antes de voltarem a agir no FIFA. Avisos de
progresso e de sucesso continuam sem capturar comandos.

Os cards de próxima partida e dados do clube usam o mesmo título de estádio,
com acentos UTF-8 e sem o sufixo de cidade/estado do scoreboard FSW. Apelidos do
estádio são preservados. O nome nos dados do clube tem espaço para duas linhas.

```powershell
python -m unittest discover -s tests -p test_career_overlay.py
cmd /c scripts\build_career_overlay.cmd
python tools/validate_career_overlay.py --game 'U:\fifa 16' --save '<snapshot>\DATA' --output '<nova-pasta>'
python tools/validate_career_overlay.py --player-only --game 'U:\fifa 16' --save '<carreira-jogador>\DATA' --output '<nova-pasta>'
```

Os verificadores offline geram cópias e conferem que o original permaneceu intacto.
O teste de jogador sintético deriva uma carreira de jogador de um snapshot de treinador;
`--player-only` também verifica uma cópia de uma carreira de jogador real.
Eles não confirmam a experiência de recarregar o resultado dentro do FIFA.

O build completo usual inclui o worker na distribuição pelo `Server16Python.spec`.
Reinicie FIFA e Server ao trocar a versão, pois o atalho de carreira usa o novo modo 3
da ponte nativa. Não execute duas instâncias do Server ao mesmo tempo. O inventário
de módulos e um objeto de posse por processo impedem injetar outra cópia de
career_jobs_runtime.dll após reabrir o Server, mesmo com canal sem resposta.

A revisão v4 verifica protocolo, reentrada, substituição de proposta/candidatura,
preservação da proposta anterior quando o destino é inválido e ausência de
recriação após expiração simulada. Os testes cobrem também o evento nativo de
assinatura, menu ocupado, cancelamento na troca de carreira e callback no thread
estável do motor. O retorno positivo da fila confirma a solicitação da tela;
a exibição dos botões e a assinatura real no FIFA ainda exigem validação.
