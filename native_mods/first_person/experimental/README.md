# Experimentos em RAM — 19/10/2026

Não são carregados pelo Server16, nem incluídos no EXE ou no build da DLL v11.

- `head_ram.cpp`: teste v12 de ocultação da cabeça do jogador controlado e recuo de 12 cm. O usuário confirmou melhora de enquadramento e ausência de cabelo. Copia o wrapper nativo completo de 232 bytes, preserva metadados e mantém LOD3 original para sombra. Restauração ao trocar jogador ainda exige validação visual completa.
- `anchor_final_v3.cpp`: tentativa de corrigir a transição ao sair do CameraModule. O usuário confirmou que o atraso continua na saída de bola e após gol; não é solução aprovada.
- `anchor_frame_v4.cpp`: observador do frame final do BCEngine. Não modifica a câmera; investigação interrompida antes da validação dessas duas situações.

A ordem usada no teste foi v11 → head v12 → um único experimento de âncora. Parar primeiro a âncora antes de remover o hook v12. F11 desativa a ocultação/recuo do teste v12. Esses arquivos dependem dos offsets e ABIs do FIFA 16 577DE45C e não devem ser ativados automaticamente. O problema de atraso continua pendente.
