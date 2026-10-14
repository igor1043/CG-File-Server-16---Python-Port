# Server16 Python — FIFA Friends

Painel para configurar partidas do FIFA 16, escolher estádios e administrar apresentação, cânticos e áudio. Trabalha com os módulos do [FIFA Friends V12](https://github.com/igor1043/fifa-mods/tree/fifa-friends-v12).

## O que está disponível

| Recurso | Funcionamento |
|---|---|
| **Configurações da partida** | Liga ou desliga mascotes, pirotecnia, fogos na entrada, fogos nos gols e objetos de abertura da competição. Aplicar salva; Voltar cancela. |
| **Objetos de abertura** | Prepara o conjunto pelo ID da competição e da fase. Em amistosos, dois clubes da mesma liga usam a entrada dessa liga. O padrão é Sim; modelo ausente ou inválido deixa a partida sem o conjunto. |
| **Estádio** | Escolha para o confronto com busca, prévia e navegação por teclado, mouse ou controle. |
| **Placar e TV** | Usa os pacotes associados à competição e à fase. |
| **Público** | Ajusta a ocupação quando o módulo nativo confirma a comunicação. |
| **Cânticos e hinos** | Usa os áudios dos clubes, perfis de volume e cânticos de rivalidade. |
| **Narração** | Escolhe os perfis externos disponíveis; os bancos de áudio são separados. |
| **Música de abertura** | Usa o perfil externo configurado para a apresentação. |
| **Câmeras e vídeos** | Aplica os pacotes configurados para a partida. |

As abas **Próxima Partida**, **Meu Time** e **Competição**, a cabine do VAR, mascotes, bolas extras e outros objetos 3D são implementados pelo V12. Este Server fornece a configuração e a seleção dos recursos correspondentes.

## Como usar

1. Abra `Server16Python.exe` e selecione a instalação do FIFA.
2. Deixe o Server aberto e inicie o FIFA 16.
3. No pré-jogo, abra o painel com **F12** ou **Start**, conforme o contexto.
4. Use os cartões de estádio, público e configurações. Confirme em **Aplicar** para salvar.
5. Depois de trocar o executável ou uma DLL, reinicie os programas envolvidos.

As opções de apresentação ficam em `ModCarrerMode/config/match_presentation.ini`. A competição e a fase usam os IDs de `FSW/settings.ini`; o Server valida e seleciona os assets locais em `data/sceneassets/entrance_props/`. A pasta local `runtime/` guarda diagnósticos da sessão.

## Executar pelos fontes

Requer Windows, Python 3.10 ou superior e FIFA 16 compatível. Instale as dependências e execute:

```powershell
python -m pip install psutil pillow pygame rarfile pyinstaller pythonnet
python main.py
```

`build_exe.bat` e `Server16Python.spec` preparam o executável. As bibliotecas nativas exigidas pelo build precisam estar em `bin/`; os nomes estão no `.spec`. Um pacote só de código não inclui essas bibliotecas nem os assets de apresentação.

## Organização e testes

- `server16_py/`: aplicativo, painéis e contexto da partida.
- `server16_py/entrance_props_runtime.py`: seleção e validação dos objetos da competição.
- `native_mods/`: fontes das integrações nativas do Server.
- `tests/`: testes sem abrir o FIFA.
- `tools/`: preparação e edição.
- [Roteiro de uso](docs/ROTEIRO_FIFA_FRIENDS.md): instruções detalhadas.

Modelos, texturas, áudio, vídeos, retratos, caches e arquivos pessoais permanecem locais. Uma falha na seleção opcional dos objetos de abertura preserva os outros recursos da partida.

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

`scripts/export_code.py` gera um ZIP de fontes, configurações e documentação sem assets ou executáveis. O ZIP precisa ser compilado antes de usar no jogo.
