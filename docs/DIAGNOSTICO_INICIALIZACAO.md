# Diagnóstico da inicialização — Server16 0.2.11

O Server16 registra cada execução do FIFA em `runtime/diagnostics/`, na pasta
do Server. Abra o jogo pelo Server atualizado e reproduza a falha. Ao observar
o encerramento do FIFA, ele cria um ZIP com data, horário e PID no nome. Se o
Server também for fechado, ele tenta concluir o relatório antes de sair.

Envie o ZIP e o `crash.dmp` da **mesma tentativa**. Se houver interrupção do
Windows antes da conclusão do ZIP, a pasta com o mesmo nome conserva o que já
foi gravado. Não é preciso trocar outros arquivos para ativar o diagnóstico:
a referência acompanha o executável do Server.

O pacote inclui:

- `LEIA-ME.txt`: resumo legível, última tela, saída do processo, DLLs gráficas
  extras e arquivos ausentes ou divergentes.
- `summary.json`: identificação da execução, versão/hash do Server, sistema,
  memória observada e estado da coleta, incluindo se a auditoria terminou.
- `timeline.jsonl`: horários com milissegundos, transições de tela, tentativas
  de leitura ainda pendentes, módulos detectados e encerramento observado.
- `files.json`: comparação SHA-256 com 729 arquivos da instalação de referência,
  incluindo interface global, overlays, DLLs dos mods e três BIGs originais
  da faixa online. Índices BH e arquivos nativos têm identificação própria,
  pois podem variar em instalações com outros mods.
- `modules.json`: módulos detectados durante a execução, caminho, endereço,
  tamanho, versão, produto e hash dos módulos locais. Drivers do sistema têm
  metadados; os módulos com referência também têm o hash verificado. Isso ajuda
  a identificar ReShade, cópias antigas em `_MEI` e DLLs de outro diretório.
- `mod_logs/`: cópias de até 1 MB de cada log disponível do loader, host,
  interface, Swiss Delta, Server e ReShade. Não inclui saves nem arquivos de
  configuração com credenciais. Caminhos locais podem identificar o usuário.

A coleta roda fora do FIFA, em thread do Server, sem injetar DLL, modificar RAM,
substituir arquivos, ativar mods ou alterar preferências. A auditoria lê cerca
de 195 MB de arquivos uma vez por execução. Os módulos são observados a cada
2 segundos nos três primeiros minutos e a cada 15 segundos depois. As sessões
ficam preservadas; cada linha de tempo tem limite de 10 mil eventos comuns.

Diferença de hash não prova a causa de um crash. Código de saída também não
identifica sozinho o culpado; o FIFA pode tratar a exceção antes de encerrar.
Uma coleta interrompida ou sem referência é marcada como tal. Não existe
remoção automática de arquivos nem tentativa automática de reparar o jogo.

## Teste do Robson

O último dump fornecido caiu em `nvwgf2umx.dll + 0x157A799` (driver NVIDIA).
Os três anteriores caíram em `fifa16.exe + 0x3A5E4F2`, na interface APT.
O último também carregava `C:\Origin Games\FIFA 16\dxgi.dll`, versão 6.5.1.2011,
ausente na instalação funcional do Igor. A versão sugere ReShade; a causa ainda
não está confirmada.

Um teste isolado é fechar o FIFA, renomear **somente a `dxgi.dll` da pasta do
jogo** para `dxgi.dll.desativado` e abrir pelo Server atualizado. Para reverter,
fechar o FIFA e devolver o nome. Não alterar a `dxgi.dll` do Windows nem
`nvwgf2umx.dll`. Comparar o relatório e o dump da nova tentativa antes de
atribuir a falha ao driver, à interface ou a um mod.
