# Conversor de abertura — FIFA Friends

Abra ConversorAberturaFIFA16.exe, arraste um vídeo para a janela, escolha a pasta
de destino e clique em Converter vídeo. Também pode arrastar o vídeo sobre o EXE.
Não é preciso instalar Python ou FFmpeg para usar o executável.

O resultado é bootflowoutro.vp8, em WebM/VP8 perfil padrão, 1080p, 29,97 FPS,
com áudio Vorbis estéreo a 48 kHz quando a origem tem áudio. Vídeos de outra
proporção recebem barras para preservar a imagem. A duração completa é mantida.
O perfil de 8 Mbps usa o FFmpeg histórico do CG File Explorer 16 e os parâmetros
que funcionaram no teste local. O bitrate é alvo, não uma garantia de bitrate
constante; 12 e 16 Mbps são experimentais. Bitrate maior não recupera detalhes
perdidos na origem. O vídeo é decodificado integralmente antes da publicação.

Para substituir uma abertura existente, selecione a sua pasta MoviesGBD/Nome.
Feche FIFA e Server antes de escolher uma pasta do jogo. O programa não instala
automaticamente no destino data/movies; o Server aplica a abertura selecionada.

Se a pasta já tem bumper.big, deixe o campo opcional vazio. Para uma nova pasta,
escolha um bumper.big existente compatível; ele será copiado, não gerado.
Depois configure essa abertura no Server16. A conversão não altera settings.ini,
DLLs, o executável do jogo ou arquivos de navegação.

Arquivos substituídos ficam em backups-conversor/data_hora dentro do destino.
Cancelamentos e falhas de conversão não publicam o vídeo parcial. conversao.log
registra a saída do FFmpeg. A reprodução de cada arquivo precisa ser testada no FIFA.
Arrastar arquivos pode ser bloqueado pelo Windows se o conversor for executado
como administrador e o Explorer não; execute normalmente ou use Escolher vídeo.

Fonte: conversor.py (Python 3.10+, biblioteca padrão). Execute com python conversor.py,
mantendo ffmpeg.exe junto ao fonte. Compilação:

    python -m PyInstaller --noconfirm --clean --onefile --windowed --name ConversorAberturaFIFA16 --add-data "ffmpeg.exe;." conversor.py

FFmpeg incluído: N-75924-gd25c033, libvpx 1.4.0, Lavf57.3.100. Binário histórico
compilado com GPL e version3; não é código de autoria deste projeto.
Informações de licença e obtenção de fontes: https://ffmpeg.org/legal.html
Revisão do projeto upstream: https://github.com/FFmpeg/FFmpeg/commit/d25c033
Parâmetros VP8: https://www.webmproject.org/docs/encoder-parameters/
