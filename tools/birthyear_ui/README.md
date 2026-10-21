# Ano de nascimento: ativação da interface

O módulo `birthyear_range_2006_2012.dll` ajusta os limites nativos. O payload
`vpro_proinfo.big` desbloqueia somente o ano e oferece os valores de 2006 a 2012.
Os dois precisam estar ativos. Copiar o BIG solto não basta se o índice BH ainda
apontar para a interface original empacotada.

Em 21/10/2026, a leitura da RAM encontrou a função `initOptData` original,
enquanto a DLL confirmava limites 2006–2012. O BIG modificado estava correto e
idêntico às branches antigas; faltava desativar sua entrada no BH.

`Enable-BirthyearUI.ps1` procura o caminho pelo diretório dos BIGs instalados,
confere o formato e a correspondência de todos os registros BH/BIG e zera
somente os oito bytes do hash da entrada. Não depende de posição fixa nem de
um BH copiado de outro computador. A preferência por arquivos soltos segue o
funcionamento descrito pelo autor do
[FHL BH Editor](https://soccergaming.com/forums/threads/fhl-bh-editor-regenerator-included.166447/).

```powershell
& .\Enable-BirthyearUI.ps1 -GameDirectory 'U:\fifa 16' -VerifyOnly
& .\Enable-BirthyearUI.ps1 -GameDirectory 'U:\fifa 16'
```

O script exige o payload de interface validado. Salva o BH anterior e um
registro em `ModCarrerMode/backups/birthyear_ui_*`, valida o resultado e não
escreve novamente quando já está aplicado. Reinicie o FIFA para descartar a
interface antiga da memória. O instalador V12 executa essa ativação após copiar
o payload; não é necessário distribuir o BH completo.

Para restaurar, com o FIFA fechado, copie o BH do backup ao caminho original,
desde que não tenha havido outra regeneração depois. Se outros mods alteraram
o índice, preserve essas alterações em vez de substituir todo o arquivo.

Validação: dez testes isolados cobrem consulta sem escrita, alteração só da
entrada correta, ordem diferente, backup, reinstalação, archive de patch,
payload desconhecido, BH ausente/incompatível e validação antes das escritas.
O teste do pacote também cobre a ativação na instalação. A execução offline
da interface confirmou ano editável, cadeado oculto e demais permissões
preservadas. A confirmação visual no jogo e a persistência em um save novo
continuam pendentes; nenhum save é alterado por esse reparo.

Para rodar os testes em outro checkout, informe `FIFA_BIRTHYEAR_PAYLOAD` com o
caminho do payload validado e execute:

```powershell
python -m unittest discover -s tests -p test_birthyear_ui_index.py -v
```
