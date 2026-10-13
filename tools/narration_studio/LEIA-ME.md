# FIFA 16 Narration Studio

O Server16 instalado está em `U:\fifa 16\Server16Python.exe`. Na prévia da
partida, pressione **Start → Escolha os narradores → Vilani → Aplicar**.
O painel aguarda a confirmação da DLL, fecha e exibe **Narração aplicada**
à direita. Depois dessa instalação inicial, é possível trocar o narrador
na prévia de outra partida sem reiniciar o FIFA.

O direcional e o analógico navegam conforme a posição dos botões. A confirma,
B volta. No teclado, F12 abre o menu; F1 público, F2 estádio, F3 configurações,
F4 narradores e F5 fecha. Setas e Enter também funcionam.

## Criar ou editar uma narração

Abra `Abrir Narration Studio.cmd`, ou o atalho de mesmo nome em
`U:\fifa 16\Narrations`. A ferramenta trabalha com o catálogo local em
`catalog.sqlite` e com os WAVs já decodificados em `original_wav`.

1. Selecione Vilani, Luiz Roberto ou **Novo narrador**.
2. Filtre por assunto: abertura, ataque, defesa, gols, faltas, bola parada,
   comentários de jogadores, call names, clubes, intervalo ou outros.
3. À esquerda, selecione a ocorrência original e ouça seu áudio. À direita,
   escolha uma gravação da biblioteca ou use **Importar MP3 / WAV**.
4. Confira e edite as transcrições quando necessário. **Vincular à ocorrência
   selecionada** salva uma associação manual; aliases do mesmo áudio físico
   recebem a mesma gravação.
5. **Gerar pacote para o jogo** converte as gravações e salva o projeto em
   `U:\fifa 16\Narrations\<nome>`. Na prévia, aplique esse narrador novamente.

As listas têm busca e páginas de 500 itens. **Associar todas as falas base**
procura correspondências por evento e significado. Preserva associações
manuais, exclui nomes de jogadores/clubes e marca aproximações para revisão.
**Transcrever pendentes** usa Whisper local no projeto selecionado. O primeiro
uso dos modelos pode baixar arquivos; nenhum áudio é enviado a um serviço.

Os projetos de Vilani e Luiz Roberto usam agora uma revisão para falas genéricas.
Boas-vindas, escalação e expectativa possuem bibliotecas próprias. A associação
automática rejeita eventos específicos, nomes encontrados na base instalada
do FIFA, referências conhecidas a jogadores e conversas de TV/publicidade.
Uma associação por assunto também não pode usar fala de gol na apresentação.
As referências em português, textos original/novo e motivos de rejeição ficam
em `transcriptions/<narrador>_base_associations.json`.

`generic_curated.json` registra as gravações aprovadas para cada momento. No
Luiz Roberto, `source/generic_curated/segment_origins.json` documenta trechos
de frases completas extraídos das gravações fornecidas, com seus intervalos.
As gravações completas originais são preservadas. Após regerar um pacote,
selecione o narrador e aplique novamente na prévia para carregar a revisão.

## Arquivos de um projeto

- `narrator.txt`: campos `Narrador=`, `Comentarista=`, `Pacote=profile.npack`
  e `Versao=2`. O Server lê os nomes desse TXT.
- `profile.npack`: banco de substituições com os áudios SPS completos.
- `profile.json`: quantidade de associações e metadados de carregamento.
- `associations.txt`: ocorrência, assunto, caminhos, transcrições e confiança.
- `build_report.json`: resultado de cada associação; `build_progress.json`
  acompanha a geração.
- `source`: arquivos importados pelo usuário; `encoded`: cache de conversão.

Tiago Leifert usa o áudio do FIFA instalado. Seu `original_catalog.tsv` contém
as 47.440 referências lógicas encontradas. Foram decodificados 46.162 áudios
físicos, sem falhas; referências diferentes podem compartilhar um áudio.
As transcrições automáticas ainda estão sendo preenchidas e aparecem como
`[pendente]` enquanto não estiverem prontas.

## Reprodução e cobertura

A DLL redireciona a reprodução para um SPS completo em memória. A duração vem
da gravação nova, sem cortar ou preencher para caber no tamanho do áudio
original. A conversão verifica a duração decodificando o SPS novamente.
A transição entre eventos e a escuta completa ainda precisam ser avaliadas
em partidas reais.

Estes são projetos de testes: uma frase semelhante pode aparecer em mais de
uma ocorrência. Falas sem associação, inclusive nomes de jogadores, continuam
com o original. A seleção é permitida na prévia; o carregador confere a
assinatura do executável suportado antes de instalar o hook. Os arquivos BIG
originais do jogo não são regravados. Os pacotes têm limite de 512 MiB.

## Dependências e caminhos

Esta instalação usa Python 3.13, FFmpeg no PATH, faster-whisper e NumPy.
As associações semânticas usam sentence-transformers na `.venv` da ferramenta;
`Instalar dependências.cmd` prepara esse ambiente. O executável do Server é
independente desse Python.

Os caminhos do jogo, vgmstream e EA Sound Exchange ficam no início de
`core.py`: jogo em `U:\fifa 16` e ferramentas na pasta FIFA16AudioTool informada
pelo usuário em J:. Para transferir a ferramenta a outra instalação, ajuste
esses caminhos e preserve o catálogo junto dos WAVs e arquivos fonte.

Os TXT de transcrição ficam em `transcriptions`. A tarefa geral em andamento
registra seu estado em `transcribe_batch_progress.json`; pode ser retomada
sem refazer os itens já salvos. Evite iniciar uma segunda transcrição enquanto
a tarefa geral estiver ativa.

Referências das bibliotecas utilizadas:
[vgmstream](https://github.com/vgmstream/vgmstream),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[modelo multilíngue de associação](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
