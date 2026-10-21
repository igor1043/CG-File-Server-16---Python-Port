# Logo no menu inicial e no cabeçalho da carreira

> Desativado em 21/10/2026 por solicitação do usuário, para isolar o crash
> recorrente do Robson. As três interfaces anteriores foram restauradas. Os
> arquivos modificados ficam em `ModCarrerMode/disabled/career_branding/` e os
> fontes permanecem disponíveis. `Disable-CareerBranding.ps1 -GameRoot PASTA`
> aplica a mesma restauração com backup; não há uma DLL dessa funcionalidade.

Substitui a faixa superior direita dos hubs inicial e da carreira pela logo enviada pelo
usuário. O globo com X, a mensagem de reconexão, o escudo EA, a tecla Q/RS e
o painel branco ficam ocultos juntos. A arte mantém a transparência sobre o
estádio. Não há overlay externo nem DLL nova.
A borda direita da logo acompanha a borda dos cards, em X=1811 no layout nativo;
o topo fica em Y=73 e a altura permanece em 79 pixels, preservando a proporção.

## Arquivos em execução

- `data/ui/game/components/careercomponents/careerhubwidget.big`: preserva o
  cabeçalho do clube e os gráficos de treinador já modificados; acrescenta a
  logo e controla sua exibição ao receber os dados da carreira.
- `data/ui/pow/components/easfcwidget.big`: preserva a implementação original
  do widget e seus provedores. A raiz da faixa nasce transparente no próprio
  APT; a opacidade zero é reforçada após atualizações da conexão, inclusive
  entre telas, para impedir que o card pisque antes da logo aparecer.
- `data/ui/game/widgets/mainhubwidget.big`: preserva a arte e o funcionamento
  do widget inicial e acrescenta a mesma logo alinhada à carreira. O construtor
  nativo ativa a ocultação, com o registro explícito da instância atual, sem
  depender de ações da timeline nem de publicação do provedor EA Access.
  Publicações posteriores reaplicam a ocultação enquanto esse menu for o dono.

Ao descarregar o cabeçalho, restaura o estado lógico de visibilidade anterior
do widget, mantendo a faixa transparente. O hub de torneio, que reutiliza a
mesma classe, não recebe a logo da carreira.
Inicialização repetida e descarregamento atrasado de uma instância antiga
não devem sobrescrever a instância atual.
A transição entre menu inicial e carreira transfere a propriedade da ocultação,
evitando que a saída atrasada da tela anterior restaure a faixa sobre a nova tela.

## Gerar e verificar

Com Python, Pillow e os utilitários locais do ScoreboardStudio:

```powershell
python build.py --studio 'U:/fifa 16/ScoreboardStudio' --output 'C:/Temp/career-branding'
python verify.py --studio 'U:/fifa 16/ScoreboardStudio' --output 'C:/Temp/career-branding'
```

`assets/logo.png` é a imagem fornecida, sem alterações no arquivo original.
O gerador converte uma cópia para DDS DXT5 e incorpora a textura ao BIG.
`originals/` guarda as bases anteriores deste ajuste, verificadas por SHA256.
O cabeçalho base já contém personalizações do FIFA Friends; não é uma cópia
genérica para substituir outras versões sem revisão.
O widget EA também parte da versão solta personalizada que já estava no jogo;
sua base foi apenas comprimida com chunkzip, preservando os 55 recursos internos.

O gerador trabalha somente em arquivos, sem abrir o jogo ou escrever na RAM.
Preserva todos os recursos existentes além dos pontos de integração APT.
Os arquivos BIG gerados são pequenos e acompanham o pacote normal do V12.

## Validação de 21/10/2026

Leitura da RAM confirmou as classes carregadas no FIFA aberto. O teste local
da máquina de ações APT verificou entrada, saída, repetição de dados, atualização
da conexão, recriação do widget, modo torneio, ausência do widget e inicialização
repetida. Também foi verificada a textura com transparência e a preservação dos
recursos anteriores. **O usuário confirmou a revisão 7 dentro do FIFA, incluindo
as transições entre telas, em 21/10/2026.**
O usuário confirmou a logo e a ocultação da faixa na carreira com a revisão 2.
A revisão 3 acrescentou a logo ao menu inicial e o alinhamento à direita. O usuário
confirmou a logo no menu inicial, mas a faixa original continuou por baixo.
A revisão 4 remove a dependência da ação do primeiro quadro e chama a ocultação
no fim do construtor nativo do menu. Os testes executam esse construtor completo,
incluindo o caso em que o widget EASFC só aparece depois. Publicações atrasadas de
um menu anterior não roubam a ocultação de uma carreira já ativa. A revisão 4
mantém idênticos os arquivos da carreira e do widget EASFC da revisão 3 e altera
apenas o widget do menu inicial. A revisão 4 falhou na abertura: o preenchimento
com zeros ao fim do construtor foi interpretado como instruções `End` pelo
preparador de ponteiros do FIFA. A leitura da RAM mostrou o nome do construtor
corretamente preparado e os nomes de todas as funções seguintes ainda como
offsets, incluindo o endereço `0xB40` que causou a falha.

A revisão 5 corrige diretamente esses cinco bytes, usando instruções neutras
`Undefined/Pop` no preenchimento. Mantém o tamanho do arquivo e todos os outros
bytes da revisão 4, incluindo logo, alinhamento e ocultação pelo construtor.
O teste agora rejeita instruções `End` internas em funções; a revisão 4 falha
nesse teste e a revisão 5 passa. O usuário confirmou que a revisão 5 abre sem
crash, mas a faixa original ainda aparece no menu inicial.

A revisão 6 corrige o acesso ao objeto global. A leitura dos handlers na RAM
do FIFA identificou `0x58` criando uma string com o conteúdo `_global`, enquanto
`0x71` empilha o objeto global real. O gerador usava `0x58` ao guardar e consultar
o dono da ocultação. A carreira escondia o widget diretamente ao receber os
dados, mas o registro entre componentes não persistia; a criação posterior ou
atualização do widget EA no menu inicial não encontrava um dono ativo.
Agora esses nove acessos usam `0x71`, como o código original do jogo. Todos os
outros bytes APT e recursos internos da revisão 5 ficam idênticos, incluindo
logo, alinhamento e correção do crash. Os três BIG mantêm o mesmo tamanho.

O teste local agora distingue a string do objeto global, em vez de aceitar os
dois opcodes como equivalentes. A revisão 5 falha nesse teste, reproduzindo a
ausência de propriedade da ocultação; a revisão 6 passa em todos os fluxos de
criação tardia, atualização de conexão e transição entre hubs. O usuário
confirmou visualmente a revisão 6 dentro do FIFA em 21/10/2026.

Na transição entre telas, o usuário observou que a faixa original ainda piscava
antes da logo. A revisão 7 mantém idênticos os BIG da carreira e do menu inicial
da revisão 6. Só altera o widget EA: aplica uma transformação de cor na
colocação inicial da raiz (`HasColorTransform`, multiplicador alfa zero e
deslocamento alfa zero), antes do primeiro desenho. As atualizações nativas
também terminam com `_alpha=0`, mesmo quando não há um cabeçalho ativo.
Assim a faixa continua transparente durante a criação tardia da logo, na
saída de uma tela e no intervalo até a próxima. Essa transparência vale
também nas demais telas que usam a mesma faixa EA.

O teste agora cobre o estado anterior ao construtor, a ausência de dono entre
hubs e atualizações nativas que voltam a definir opacidade. A revisão 6 falha
na verificação da colocação inicial; a revisão 7 passa. Os 55 recursos internos
anteriores continuam preservados, exceto pelos pontos APT descritos. A
validação visual das transições da revisão 7 foi confirmada pelo usuário
dentro do FIFA em 21/10/2026: o card deixou de piscar entre telas.

A primeira instalação falhou na abertura. O dump e a leitura da RAM localizaram
a instrução exata: `Function2.name` era nulo e o carregador em
`FIFA16+0x3a5e4f2` tentava ler seu primeiro caractere. A revisão 2 usa um ponteiro
válido para uma string vazia e tabelas de parâmetros válidas, inclusive nas
funções sem argumentos. A verificação agora rejeita referências nulas nesses
campos. A consulta da classe na inicialização também verifica cada namespace
antes de percorrer seus membros. O usuário confirmou abertura e funcionamento
da carreira na revisão 2.

Os arquivos já carregados ficam em cache; reabrir o FIFA garante o carregamento
da nova interface. A reversão restaura os arquivos anteriores registrados no
manifesto do backup. No jogo, as cópias soltas já existentes são restauradas;
no pacote de desenvolvimento, os overrides que não existiam antes são retirados.
O widget original continua no arquivo grande
do jogo, que não é modificado.
